"""RoadSense detection, incident, location, and notification service."""

import asyncio
import base64
import html
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from typing import Literal
from urllib.parse import quote, quote_plus, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

import cv2
import numpy as np
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request as FastAPIRequest, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import ExifTags, Image
from pillow_heif import register_heif_opener
from psycopg.rows import dict_row
import psycopg
from pydantic import BaseModel, Field

# Keep Ultralytics settings inside this project. Some Windows profiles restrict
# writes to the default AppData location used by the library.
os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(__file__).resolve().parent / ".ultralytics"))
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parents[2]


def load_local_env() -> None:
    """Load local development secrets without overriding exported environment values."""
    env_file = Path(__file__).with_name(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_local_env()
# Allow Pillow to open HEIC/HEIF uploads while retaining normal JPEG/PNG support.
register_heif_opener()
DATA_DIR = Path(os.getenv("ROADSENSE_DATA_DIR", Path(__file__).resolve().parent / "data"))
MEDIA_DIR, DB_PATH = DATA_DIR / "media", DATA_DIR / "roadsense.db"


def normalize_database_url(value: str) -> str:
    """Safely encode a password containing URI-special characters such as @."""
    if not value.startswith(("postgresql://", "postgres://")):
        return value
    scheme, remainder = value.split("://", 1)
    credentials, separator, host = remainder.rpartition("@")
    if not separator or ":" not in credentials:
        return value
    username, password = credentials.split(":", 1)
    return f"{scheme}://{username}:{quote(unquote(password), safe='')}@{host}"


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", "").strip())
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_STORAGE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_SECRET_KEY", "")).strip()
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "incident-media").strip()
FRONTEND_DIST = BASE_DIR / "road_sense_web" / "roadsense_frontend" / "dist" / "public"


def storage_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_STORAGE_KEY and SUPABASE_STORAGE_BUCKET)


def storage_object_url(filename: str) -> str:
    safe_name = Path(filename).name
    return f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_STORAGE_BUCKET, safe='')}/{quote(safe_name, safe='')}"


def store_media(filename: str, content: bytes, content_type: str) -> None:
    """Keep a local copy for immediate use and mirror it into private Supabase Storage."""
    safe_name = Path(filename).name
    (MEDIA_DIR / safe_name).write_bytes(content)
    if not storage_enabled():
        return
    request = Request(
        storage_object_url(safe_name),
        data=content,
        method="POST",
        headers={
            "Authorization": f"Bearer {SUPABASE_STORAGE_KEY}",
            "apikey": SUPABASE_STORAGE_KEY,
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        },
    )
    try:
        with urlopen(request, timeout=30):
            pass
    except Exception as error:
        # The local file remains available, so reporting and live detection continue.
        print(f"Supabase Storage upload failed for {safe_name}: {error}")


def load_media(filename: str) -> tuple[bytes | None, str]:
    """Read local evidence first, then recover it from private Supabase Storage."""
    safe_name = Path(filename).name
    path = MEDIA_DIR / safe_name
    mime_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    if path.exists():
        return path.read_bytes(), mime_type
    if not storage_enabled():
        return None, mime_type
    request = Request(storage_object_url(safe_name), headers={"Authorization": f"Bearer {SUPABASE_STORAGE_KEY}", "apikey": SUPABASE_STORAGE_KEY})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read(), response.headers.get_content_type() or mime_type
    except Exception:
        return None, mime_type


def delete_media(filename: str) -> None:
    safe_name = Path(filename).name
    path = MEDIA_DIR / safe_name
    if path.exists():
        path.unlink()
    if not storage_enabled():
        return
    request = Request(
        f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_STORAGE_BUCKET, safe='')}",
        data=json.dumps({"prefixes": [safe_name]}).encode("utf-8"),
        method="DELETE",
        headers={"Authorization": f"Bearer {SUPABASE_STORAGE_KEY}", "apikey": SUPABASE_STORAGE_KEY, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30):
            pass
    except Exception:
        pass
def discover_models() -> dict[str, Path]:
    """Load the bundled models and any later model dropped into runs/<name>/weights/best.pt."""
    discovered = {
        "v1": BASE_DIR / "runs" / "pothole_manhole_v1" / "weights" / "best.pt",
        "v2": BASE_DIR / "runs" / "pothole_manhole_v2_augmented" / "weights" / "best.pt",
    }
    for weights in (BASE_DIR / "runs").glob("*/weights/best.pt"):
        if weights not in discovered.values():
            discovered[weights.parents[1].name] = weights
    configured = os.getenv("ROADSENSE_MODELS", "").strip()
    if configured:
        for name, path in json.loads(configured).items():
            discovered[str(name)] = Path(path)
    return discovered


MODELS = discover_models()
DEFAULT_MODEL = "roadsense_v8" if "roadsense_v8" in MODELS and MODELS["roadsense_v8"].exists() else "v2"
EMAIL_PATTERN = re.compile(r"^(?=.{3,254}$)(?=.{1,64}@)[A-Z0-9](?:[A-Z0-9._%+-]{0,62}[A-Z0-9])?@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized_email(value: str) -> str:
    email = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(email) or ".." in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    return email


def connect_local_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


class PostgresDatabase:
    """Small compatibility layer while RoadSense transitions from SQLite to PostgreSQL."""
    def __init__(self) -> None:
        self.connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def execute(self, query: str, parameters: tuple | list | None = None):
        # RoadSense's existing SQL uses DB-API qmark placeholders; psycopg uses %s.
        converted = re.sub(r"\?", "%s", query)
        return self.connection.execute(converted, parameters or ())

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)


def connect_db():
    if DATABASE_URL:
        try:
            return PostgresDatabase()
        except psycopg.OperationalError:
            # Keep the MVP available if a cloud connection is temporarily unavailable.
            return connect_local_db()
    return connect_local_db()


def setup_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    schema = """
        CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, source_id TEXT NOT NULL, model_name TEXT NOT NULL, hazard_type TEXT NOT NULL, confidence REAL NOT NULL, latitude REAL, longitude REAL, accuracy_m REAL, status TEXT NOT NULL DEFAULT 'open', details TEXT, image_path TEXT, detection_count INTEGER NOT NULL, reporter_name TEXT, reporter_email TEXT, location_name TEXT, address_line TEXT, area TEXT, city TEXT, postal_code TEXT, landmark TEXT, location_source TEXT);
        CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL, captured_at TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL, accuracy_m REAL, heading REAL, speed_kph REAL);
        CREATE TABLE IF NOT EXISTS authorities (id TEXT PRIMARY KEY, name TEXT NOT NULL, jurisdiction TEXT, email TEXT, phone TEXT, whatsapp_enabled INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, authority_id TEXT NOT NULL, channel TEXT NOT NULL, status TEXT NOT NULL, detail TEXT, sent_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS oauth_states (state TEXT PRIMARY KEY, return_to TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS google_accounts (email TEXT PRIMARY KEY, access_token TEXT NOT NULL, refresh_token TEXT NOT NULL, expires_at REAL NOT NULL, display_name TEXT, connected_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, display_name TEXT NOT NULL, password_hash TEXT NOT NULL, notify_email INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS email_verifications (email TEXT PRIMARY KEY, display_name TEXT NOT NULL, password_hash TEXT NOT NULL, code_hash TEXT NOT NULL, expires_at REAL NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS user_sessions (id TEXT PRIMARY KEY, email TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sms_reports (message_sid TEXT PRIMARY KEY, incident_id TEXT NOT NULL, sender_phone TEXT NOT NULL, received_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS resolution_proofs (id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, authority_email TEXT NOT NULL, note TEXT NOT NULL, media_path TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS authority_updates (id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, authority_email TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS zone_alerts (zone_key TEXT NOT NULL, threshold INTEGER NOT NULL, incident_id TEXT NOT NULL, sent_at TEXT NOT NULL, PRIMARY KEY (zone_key, threshold));
        CREATE TABLE IF NOT EXISTS password_resets (token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires_at REAL NOT NULL, used_at TEXT);
        CREATE INDEX IF NOT EXISTS incidents_created_at ON incidents(created_at DESC);
        CREATE INDEX IF NOT EXISTS locations_source_time ON locations(source_id, captured_at DESC);
        """
    with connect_db() as db:
        using_postgres = isinstance(db, PostgresDatabase)
        db.executescript(schema.replace("id INTEGER PRIMARY KEY AUTOINCREMENT", "id BIGSERIAL PRIMARY KEY") if using_postgres else schema)
        if using_postgres:
            # The first cloud startup copies the local MVP data. Repeating hundreds
            # of no-op upserts on every launch can exhaust a shared pooler session.
            cloud_has_incidents = dict(db.execute("SELECT EXISTS (SELECT 1 FROM incidents) AS has_records").fetchone())["has_records"]
            if not cloud_has_incidents:
                migrate_local_records(db)
            return
        columns = {row[1] for row in db.execute("PRAGMA table_info(incidents)")}
        for name, definition in (("details", "TEXT"), ("reporter_name", "TEXT"), ("reporter_email", "TEXT"), ("location_name", "TEXT"), ("address_line", "TEXT"), ("area", "TEXT"), ("city", "TEXT"), ("postal_code", "TEXT"), ("landmark", "TEXT"), ("location_source", "TEXT")):
            if name not in columns:
                db.execute(f"ALTER TABLE incidents ADD COLUMN {name} {definition}")
        user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        if "notify_email" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN notify_email INTEGER NOT NULL DEFAULT 1")
        sms_columns = {row[1] for row in db.execute("PRAGMA table_info(sms_reports)")}
        for name, definition in (("original_body", "TEXT"), ("english_body", "TEXT")):
            if name not in sms_columns:
                db.execute(f"ALTER TABLE sms_reports ADD COLUMN {name} {definition}")
        authority_columns = {row[1] for row in db.execute("PRAGMA table_info(authorities)")}
        if "whatsapp_enabled" not in authority_columns:
            db.execute("ALTER TABLE authorities ADD COLUMN whatsapp_enabled INTEGER NOT NULL DEFAULT 0")


def ensure_default_authority() -> None:
    """Seed the configured notification recipient on startup."""
    email = os.getenv("DEFAULT_AUTHORITY_EMAIL", "").strip()
    if not email:
        return
    with connect_db() as db:
        db.execute(
            "INSERT INTO authorities (id, name, jurisdiction, email, phone, enabled, created_at) "
            "VALUES (?, ?, ?, ?, NULL, 1, ?) ON CONFLICT DO NOTHING",
            (
                "default-email-authority",
                os.getenv("DEFAULT_AUTHORITY_NAME", "RoadSense notifications"),
                "Default notification recipient",
                email,
                utc_now(),
            ),
        )


def migrate_local_records(target: PostgresDatabase) -> None:
    """Copy MVP SQLite records into Supabase without replacing newer cloud records."""
    if not DB_PATH.exists():
        return
    tables = ("users", "user_sessions", "authorities", "incidents", "locations", "notifications", "oauth_states", "google_accounts", "sms_reports", "resolution_proofs", "authority_updates", "password_resets", "zone_alerts")
    with connect_local_db() as source:
        for table in tables:
            exists = source.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
            if not exists:
                continue
            columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})").fetchall()]
            if not columns:
                continue
            placeholders = ", ".join("?" for _ in columns)
            statement = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
            for row in source.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall():
                target.execute(statement, tuple(row[column] for column in columns))
        target.execute("SELECT setval(pg_get_serial_sequence('locations', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM locations), 1), 1), true)")


class AuthorityIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    jurisdiction: str | None = Field(default=None, max_length=160)
    email: str | None = None
    phone: str | None = None
    whatsapp_enabled: bool = False
    enabled: bool = True


class LocationIn(BaseModel):
    source_id: str = Field(default="mobile", min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    heading: float | None = Field(default=None, ge=0, lt=360)
    speed_kph: float | None = Field(default=None, ge=0)
    captured_at: datetime | None = None


class StreamStartIn(BaseModel):
    source: str = Field(default="0", min_length=1, max_length=1024)
    source_id: str = Field(default="camera-1", min_length=1, max_length=80)
    model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=80)
    confidence: float = Field(default=0.35, ge=0.05, le=0.95)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    auto_notify: bool = True
    reporter_email: str | None = None


class IncidentUpdateIn(BaseModel):
    status: Literal["open", "acknowledged", "resolved", "false_positive"] | None = None
    details: str | None = Field(default=None, max_length=4000)


class AuthorityWorkUpdateIn(BaseModel):
    message: str = Field(min_length=3, max_length=1000)
    status: Literal["acknowledged", "resolved"] = "acknowledged"


class SignUpIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class SignInIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class EmailVerificationIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=6, max_length=6)


class AuthoritySignInIn(BaseModel):
    authority_id: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class PasswordResetRequestIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class PasswordResetIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=6, max_length=12)
    password: str = Field(min_length=8, max_length=256)


class PasswordResetCodeIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=6, max_length=12)


class ProfileUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notify_email: bool = True


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


def require_authority(request: FastAPIRequest) -> str:
    email = authenticated_reporter_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Sign in as an authority to access this workspace")
    with connect_db() as db:
        authorized = db.execute("SELECT 1 FROM authorities WHERE lower(email) = ? AND enabled = 1", (email.lower(),)).fetchone()
    if not authorized:
        raise HTTPException(status_code=403, detail="This account is not an enabled RoadSense authority")
    return email


class IncidentReportIn(BaseModel):
    hazard_type: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source_id: str = Field(default="citizen-report", min_length=1, max_length=80)
    reporter_name: str = Field(min_length=1, max_length=120)
    reporter_email: str | None = Field(default=None, max_length=254)
    location_name: str = Field(min_length=1, max_length=240)
    address_line: str | None = Field(default=None, max_length=240)
    area: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=20)
    landmark: str | None = Field(default=None, max_length=240)
    details: str | None = Field(default=None, max_length=4000)


class LiveHub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    async def publish(self, event: str, data: dict) -> None:
        stale = []
        message = {"event": event, "data": data, "sent_at": utc_now()}
        for client in self.clients:
            try:
                await client.send_json(message)
            except Exception:
                stale.append(client)
        for client in stale:
            self.disconnect(client)


class ModelRegistry:
    def __init__(self):
        self.loaded: dict[str, YOLO] = {}
        self.lock = threading.Lock()

    def load_available(self) -> None:
        for name, path in MODELS.items():
            if path.exists():
                self.loaded[name] = YOLO(str(path))

    def available(self, model_name: str) -> bool:
        return model_name in MODELS and MODELS[model_name].exists()

    def get_model(self, model_name: str) -> YOLO:
        if not self.available(model_name):
            raise RuntimeError(f"Model '{model_name}' is unavailable")
        with self.lock:
            if model_name not in self.loaded:
                self.loaded[model_name] = YOLO(str(MODELS[model_name]))
            return self.loaded[model_name]

    def predict(self, image: np.ndarray, model_name: str, confidence: float) -> list[dict]:
        model = self.get_model(model_name)
        with self.lock:
            result = model.predict(source=image, conf=confidence, imgsz=640, iou=0.45, verbose=False)[0]
        return [{"class": str(result.names[int(box.cls[0])]), "confidence": round(float(box.conf[0]), 4), "box": [round(float(value), 2) for value in box.xyxy[0]]} for box in result.boxes]


models, hub = ModelRegistry(), LiveHub()


def annotate(frame: np.ndarray, detections: list[dict]) -> np.ndarray:
    output = frame.copy()
    for detection in detections:
        x1, y1, x2, y2 = (int(value) for value in detection["box"])
        color = (0, 96, 255) if detection["class"].lower() == "pothole" else (0, 190, 255)
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        cv2.putText(output, f"{detection['class']} {detection['confidence']:.0%}", (x1, max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)
    return output


def extract_photo_gps(content: bytes) -> tuple[float, float] | None:
    """Read original camera GPS from an image, if the uploader preserved EXIF."""
    try:
        with Image.open(BytesIO(content)) as image:
            exif = image.getexif()
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo) or exif.get(34853, {})
        latitude_values, longitude_values = gps.get(2), gps.get(4)
        if not latitude_values or not longitude_values:
            return None
        def decimal(values: tuple[object, object, object]) -> float:
            degrees, minutes, seconds = (float(value) for value in values[:3])
            return degrees + minutes / 60 + seconds / 3600
        latitude, longitude = decimal(latitude_values), decimal(longitude_values)
        if gps.get(1) in ("S", b"S"):
            latitude = -latitude
        if gps.get(3) in ("W", b"W"):
            longitude = -longitude
        return (latitude, longitude) if -90 <= latitude <= 90 and -180 <= longitude <= 180 else None
    except Exception:
        return None


def incident_by_id(db: sqlite3.Connection, incident_id: str) -> dict:
    row = db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return dict(row)


ZONE_CELL_DEGREES = 0.015
ZONE_LEVELS = ((8, "red"), (5, "orange"), (3, "yellow"), (2, "blue"), (1, "green"))
ZONE_ALERT_THRESHOLDS = {3, 5, 8}


def zone_key(latitude: float, longitude: float) -> str:
    return f"{int(latitude // ZONE_CELL_DEGREES)}:{int(longitude // ZONE_CELL_DEGREES)}"


def zone_color(count: int) -> str:
    return next(color for threshold, color in ZONE_LEVELS if count >= threshold)


def incident_zones(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute("SELECT latitude, longitude FROM incidents WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND status != 'false_positive'").fetchall()
    grouped: dict[str, dict] = {}
    for row in rows:
        latitude, longitude = float(row["latitude"]), float(row["longitude"])
        key = zone_key(latitude, longitude)
        group = grouped.setdefault(key, {"zone_key": key, "latitude": 0.0, "longitude": 0.0, "count": 0})
        group["latitude"] += latitude
        group["longitude"] += longitude
        group["count"] += 1
    zones = []
    for group in grouped.values():
        count = group["count"]
        zones.append({**group, "latitude": group["latitude"] / count, "longitude": group["longitude"] / count, "color": zone_color(count)})
    return sorted(zones, key=lambda zone: zone["count"], reverse=True)


def notify_zone_escalation(incident_id: str) -> list[dict]:
    """Alert authorities once as nearby report density enters yellow, orange, or red."""
    with connect_db() as db:
        incident = incident_by_id(db, incident_id)
        if incident.get("latitude") is None or incident.get("longitude") is None:
            return []
        key = zone_key(float(incident["latitude"]), float(incident["longitude"]))
        zone = next((item for item in incident_zones(db) if item["zone_key"] == key), None)
        if zone is None or zone["count"] not in ZONE_ALERT_THRESHOLDS:
            return []
        try:
            db.execute("INSERT INTO zone_alerts VALUES (?, ?, ?, ?)", (key, zone["count"], incident_id, utc_now()))
        except sqlite3.IntegrityError:
            return []
        contacts = [dict(row) for row in db.execute("SELECT * FROM authorities WHERE enabled = 1 AND email IS NOT NULL AND email != ''").fetchall()]
        severity = zone["color"].upper()
        subject = f"RoadSense {severity} zone escalation: {zone['count']} nearby reports"
        map_url = f"https://www.google.com/maps?q={zone['latitude']:.6f},{zone['longitude']:.6f}"
        body = f"RoadSense has recorded {zone['count']} reports in the same local zone.\nSeverity: {severity}\nZone center: {zone['latitude']:.6f}, {zone['longitude']:.6f}\nMap: {map_url}\n\nPlease review the clustered reports in the authority portal."
        outcomes = []
        for authority in contacts:
            try:
                detail, status = send_email(authority["email"], subject, body), "sent"
            except Exception as exc:
                detail, status = str(exc), "failed"
            outcomes.append({"authority": authority["name"], "channel": "zone_email", "status": status, "detail": detail})
            db.execute("INSERT INTO notifications VALUES (?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), incident_id, authority["id"], "zone_email", status, detail, utc_now()))
        return outcomes


def record_detections(frame: np.ndarray, detections: list[dict], settings: StreamStartIn) -> list[dict]:
    created = []
    with connect_db() as db:
        for detection in detections:
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
            duplicate = db.execute("SELECT 1 FROM incidents WHERE source_id = ? AND hazard_type = ? AND created_at > ? LIMIT 1", (settings.source_id, detection["class"], cutoff)).fetchone()
            if duplicate:
                continue
            incident_id, now = str(uuid.uuid4()), utc_now()
            image_name = f"{incident_id}.jpg"
            _, encoded = cv2.imencode(".jpg", annotate(frame, [detection]), [cv2.IMWRITE_JPEG_QUALITY, 88])
            store_media(image_name, encoded.tobytes(), "image/jpeg")
            location_source = "live_camera_gps" if settings.latitude is not None and settings.longitude is not None else "not_supplied"
            db.execute("INSERT INTO incidents (id, created_at, updated_at, source_id, model_name, hazard_type, confidence, latitude, longitude, accuracy_m, status, details, image_path, detection_count, location_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'open', NULL, ?, 1, ?)", (incident_id, now, now, settings.source_id, settings.model, detection["class"], detection["confidence"], settings.latitude, settings.longitude, image_name, location_source))
            created.append(incident_by_id(db, incident_id))
    return created


def incident_map_url(incident: dict, location: str) -> tuple[str | None, str]:
    has_coordinates = incident.get("latitude") is not None and incident.get("longitude") is not None
    if has_coordinates:
        return f"https://www.google.com/maps?q={incident['latitude']:.6f},{incident['longitude']:.6f}", "GPS coordinates"
    if location and location != "Location not supplied":
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(location)}", "reported location search"
    return None, "not supplied"


def display_timestamp(value: str) -> str:
    """Render stored UTC timestamps for RoadSense recipients in India Standard Time."""
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        ist = timezone(timedelta(hours=5, minutes=30), name="IST")
        return timestamp.astimezone(ist).strftime("%d %b %Y, %I:%M:%S %p IST")
    except (TypeError, ValueError):
        return value


def notification_text(incident: dict) -> tuple[str, str, str]:
    has_coordinates = incident.get("latitude") is not None and incident.get("longitude") is not None
    coordinates = f"{incident['latitude']:.6f}, {incident['longitude']:.6f}" if has_coordinates else "Location not supplied"
    address = ", ".join(str(value) for value in (incident.get("address_line"), incident.get("area"), incident.get("city"), incident.get("postal_code")) if value)
    location = incident.get("location_name") or address or coordinates
    source_text = "reported" if incident["source_id"] == "citizen-report" else "detected"
    subject = f"RoadSense alert: {incident['hazard_type']} {source_text}"
    reporter = f"\nReported by: {incident['reporter_name']} ({incident['reporter_email'] or 'email not provided'})" if incident.get("reporter_name") else ""
    landmark = f"\nLandmark: {incident['landmark']}" if incident.get("landmark") else ""
    map_url, map_source = incident_map_url(incident, location)
    map_link = f"\nMap: {map_url}" if map_url else ""
    action = "reported" if incident["source_id"] == "citizen-report" else "detected"
    location_source = {"photo_metadata": "photo GPS metadata", "manual_pin": "manual map pin", "reporter_device": "reporter device GPS", "live_camera_gps": "live camera device GPS", "not_supplied": "not supplied"}.get(incident.get("location_source"), "report details")
    details = incident.get("details") or "Not supplied"
    recorded_at = display_timestamp(incident["created_at"])
    text = f"RoadSense {action} a {incident['hazard_type']} ({incident['confidence']:.0%} confidence).\nSource: {incident['source_id']}\nLocation: {location}\nAddress: {address or 'Not supplied'}\nDetails: {details}\nCoordinates: {coordinates}\nCoordinate source: {location_source}\nMap source: {map_source}{map_link}{landmark}{reporter}\nRecorded at: {recorded_at}\nIncident ID: {incident['id']}"
    link = f'<p><a href="{html.escape(map_url, quote=True)}" style="display:inline-block;padding:12px 16px;background:#1d4ed8;border-radius:6px;color:#ffffff;font-weight:700;text-decoration:none">Open in Google Maps</a></p>' if map_url else ""
    html_body = f"<div style=\"font-family:Arial,sans-serif;color:#17202a;line-height:1.5\"><h2>RoadSense {html.escape(incident['hazard_type'])} alert</h2><p><strong>Location:</strong> {html.escape(location)}<br><strong>Address:</strong> {html.escape(address or 'Not supplied')}<br><strong>Details:</strong> {html.escape(details)}<br><strong>Coordinates:</strong> {html.escape(coordinates)}<br><strong>Location source:</strong> {html.escape(location_source)}<br><strong>Recorded at:</strong> {html.escape(recorded_at)}</p>{link}<p style=\"color:#52606d\">Incident ID: {html.escape(incident['id'])}</p></div>"
    return subject, text, html_body


def evidence_attachment(incident: dict) -> tuple[tuple[bytes, str, str] | None, str]:
    """Build an email-safe evidence attachment; location is stamped on still images."""
    if not incident.get("image_path"):
        return None, "No evidence was captured."
    filename = Path(incident["image_path"]).name
    content, mime_type = load_media(filename)
    if content is None:
        return None, "Evidence file was unavailable when the email was prepared."
    if len(content) > 20 * 1024 * 1024:
        return None, "Evidence was not attached because it exceeds the 20 MB email limit."
    if mime_type.startswith("image/"):
        image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is not None:
            address = ", ".join(str(value) for value in (incident.get("location_name"), incident.get("address_line"), incident.get("area"), incident.get("city"), incident.get("postal_code")) if value) or "Location not supplied"
            has_coordinates = incident.get("latitude") is not None and incident.get("longitude") is not None
            coordinates = f"GPS: {incident['latitude']:.6f}, {incident['longitude']:.6f}" if has_coordinates else ""
            lines = [address[i:i + 74] for i in range(0, len(address), 74)] + ([coordinates] if coordinates else [])
            footer_height = 24 + 25 * len(lines)
            stamped = cv2.copyMakeBorder(image, 0, footer_height, 0, 0, cv2.BORDER_CONSTANT, value=(14, 22, 32))
            for index, line in enumerate(lines):
                cv2.putText(stamped, line, (14, image.shape[0] + 22 + index * 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 241, 247), 1, cv2.LINE_AA)
            ok, encoded = cv2.imencode(".jpg", stamped, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if ok:
                return (encoded.tobytes(), "image/jpeg", f"roadsense-{incident['id']}-location.jpg"), "Location-stamped evidence is attached."
    return (content, mime_type, filename), "Original evidence is attached."


def add_attachment(message: EmailMessage, attachment: tuple[bytes, str, str] | None) -> None:
    if attachment is None:
        return
    content, mime_type, filename = attachment
    maintype, _, subtype = mime_type.partition("/")
    message.add_attachment(content, maintype=maintype or "application", subtype=subtype or "octet-stream", filename=filename)


def send_email(recipient: str, subject: str, body: str, attachment: tuple[bytes, str, str] | None = None, html_body: str | None = None) -> str:
    # Render cannot reliably open outbound SMTP sockets. A connected Gmail
    # account uses Google's HTTPS API instead and remains the primary sender.
    gmail_sender = os.getenv("DEFAULT_GMAIL_SENDER", "").strip().lower()
    if gmail_sender:
        try:
            return send_gmail(gmail_sender, recipient, subject, body, attachment, html_body)
        except Exception as gmail_error:
            smtp_fallback_error = gmail_error
        else:
            smtp_fallback_error = None
    host, sender = os.getenv("SMTP_HOST"), os.getenv("SMTP_FROM")
    if not host or not sender:
        if gmail_sender:
            raise RuntimeError(f"Default Gmail sender is unavailable: {smtp_fallback_error}")
        raise RuntimeError("Email delivery is not configured")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, recipient, subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    add_attachment(message, attachment)
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as client:
            if os.getenv("SMTP_TLS", "true").lower() == "true": client.starttls()
            if os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD"): client.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            client.send_message(message)
    except OSError as smtp_error:
        if gmail_sender:
            raise RuntimeError(f"Gmail API failed ({smtp_fallback_error}); SMTP fallback failed ({smtp_error})") from smtp_error
        raise
    return "Email delivered to SMTP provider"


def google_config() -> tuple[str, str, str]:
    client_id, secret, redirect_uri = os.getenv("GOOGLE_OAUTH_CLIENT_ID"), os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"), os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    if not all([client_id, secret, redirect_uri]):
        raise RuntimeError("Google OAuth is not configured")
    return client_id, secret, redirect_uri


def google_request(url: str, *, data: dict | bytes | None = None, headers: dict | None = None) -> dict:
    payload = urlencode(data).encode() if isinstance(data, dict) else data
    request = Request(url, data=payload, headers=headers or {}, method="POST" if payload else "GET")
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def google_access_token(email: str) -> str:
    with connect_db() as db:
        account = db.execute("SELECT * FROM google_accounts WHERE email = ?", (email,)).fetchone()
        if account is None: raise RuntimeError("Reporter has not connected Gmail")
        account = dict(account)
        if account["expires_at"] > time.time() + 60: return account["access_token"]
        client_id, secret, _ = google_config()
        tokens = google_request("https://oauth2.googleapis.com/token", data={"client_id": client_id, "client_secret": secret, "refresh_token": account["refresh_token"], "grant_type": "refresh_token"})
        token, expiry = tokens["access_token"], time.time() + int(tokens.get("expires_in", 3600))
        db.execute("UPDATE google_accounts SET access_token = ?, expires_at = ? WHERE email = ?", (token, expiry, email))
        return token


def send_gmail(email: str, recipient: str, subject: str, body: str, attachment: tuple[bytes, str, str] | None = None, html_body: str | None = None) -> str:
    message = EmailMessage(); message["From"], message["To"], message["Subject"] = email, recipient, subject; message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    add_attachment(message, attachment)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
    google_request("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", data=json.dumps({"raw": raw}).encode(), headers={"Authorization": f"Bearer {google_access_token(email)}", "Content-Type": "application/json"})
    return f"Email sent from {email}"


def send_sms(recipient: str, body: str) -> str:
    sid, token, sender = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_FROM")
    if not all([sid, token, sender]):
        raise RuntimeError("Twilio is not configured")
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    request = Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=urlencode({"To": recipient, "From": sender, "Body": body}).encode(), headers={"Authorization": f"Basic {auth}"}, method="POST")
    with urlopen(request, timeout=20) as response:
        if response.status >= 300: raise RuntimeError(f"Twilio returned HTTP {response.status}")
    return "SMS accepted by Twilio"


def send_whatsapp(recipient: str, body: str) -> str:
    """Send an opted-in authority alert using a configured Twilio WhatsApp sender."""
    sid, token, sender = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_WHATSAPP_FROM")
    if not all([sid, token, sender]):
        raise RuntimeError("Twilio WhatsApp is not configured")
    destination = recipient if recipient.startswith("whatsapp:") else f"whatsapp:{recipient}"
    origin = sender if sender.startswith("whatsapp:") else f"whatsapp:{sender}"
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    request = Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=urlencode({"To": destination, "From": origin, "Body": body}).encode(), headers={"Authorization": f"Basic {auth}"}, method="POST")
    with urlopen(request, timeout=20) as response:
        if response.status >= 300:
            raise RuntimeError(f"Twilio WhatsApp returned HTTP {response.status}")
    return "WhatsApp accepted by Twilio"


def notify_authorities(incident_id: str, reporter_email: str | None = None) -> list[dict]:
    outcomes = []
    with connect_db() as db:
        incident, contacts = incident_by_id(db, incident_id), db.execute("SELECT * FROM authorities WHERE enabled = 1").fetchall()
        subject, body, html_body = notification_text(incident)
        gmail_connected = bool(reporter_email and db.execute("SELECT 1 FROM google_accounts WHERE email = ?", (reporter_email,)).fetchone())
        attachment, evidence_note = evidence_attachment(incident)
        body = f"{body}\n\nEvidence: {evidence_note}"
        for authority in map(dict, contacts):
            deliveries = [
                ("email", authority["email"], lambda: send_gmail(reporter_email, authority["email"], subject, body, attachment, html_body) if gmail_connected else send_email(authority["email"], subject, body, attachment, html_body)),
                ("sms", authority["phone"], lambda: send_sms(authority["phone"], body)),
            ]
            if authority.get("whatsapp_enabled"):
                deliveries.append(("whatsapp", authority["phone"], lambda: send_whatsapp(authority["phone"], body)))
            for channel, recipient, sender in deliveries:
                if not recipient: continue
                try: detail, status = sender(), "sent"
                except Exception as exc: detail, status = str(exc), "failed"
                outcomes.append({"authority": authority["name"], "channel": channel, "status": status, "detail": detail})
                db.execute("INSERT INTO notifications VALUES (?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), incident_id, authority["id"], channel, status, detail, utc_now()))
    return outcomes


def sms_report_parts(message: str) -> tuple[str, str, str | None]:
    """Parse: POTHOLE | road or address | optional details."""
    parts = [part.strip() for part in message.split("|", 2)]
    label = parts[0].lower() if parts else ""
    if label in {"pothole", "pot hole"}:
        hazard = "pothole"
    elif label in {"manhole", "man hole", "open manhole"}:
        hazard = "manhole"
    else:
        hazard = "other"
    location = parts[1] if len(parts) > 1 and parts[1] else "Location supplied by SMS sender"
    details = parts[2] if len(parts) > 2 and parts[2] else (None if len(parts) > 1 else message.strip() or None)
    return hazard, location[:240], details[:4000] if details else None


def translate_sms_to_english(message: str) -> str:
    """Translate arbitrary-language SMS text through a configured LibreTranslate-compatible service."""
    service_url = os.getenv("TRANSLATION_URL", "").strip()
    if not service_url:
        # Keep the accessible SMS channel usable before a translation provider
        # is configured. English reports are stored as entered.
        return message
    payload = {"q": message, "source": "auto", "target": "en", "format": "text"}
    api_key = os.getenv("TRANSLATION_API_KEY", "").strip()
    if api_key:
        payload["api_key"] = api_key
    try:
        result = google_request(service_url, data=payload)
        translated = str(result.get("translatedText", "")).strip()
    except Exception as exc:
        raise RuntimeError(f"SMS translation failed: {exc}") from exc
    if not translated:
        raise RuntimeError("SMS translation service returned no English text")
    return translated


def valid_twilio_request(request_url: str, form: dict[str, str], signature: str | None) -> bool:
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not token or not signature:
        return False
    url = os.getenv("TWILIO_SMS_WEBHOOK_URL", request_url)
    signed = url + "".join(key + form[key] for key in sorted(form))
    expected = base64.b64encode(hmac.new(token.encode(), signed.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


class StreamWorker:
    def __init__(self):
        self.thread: threading.Thread | None = None
        self.stop_event, self.lock = threading.Event(), threading.Lock()
        self.latest_jpeg: bytes | None = None
        self.status = {"running": False, "source_id": None, "fps": 0, "error": None}

    def start(self, settings: StreamStartIn, loop: asyncio.AbstractEventLoop) -> None:
        self.stop(); self.stop_event.clear()
        self.status = {"running": True, "source_id": settings.source_id, "fps": 0, "error": None, "model": settings.model}
        self.thread = threading.Thread(target=self._run, args=(settings, loop), daemon=True); self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive(): self.thread.join(timeout=3)
        self.thread = None; self.status["running"] = False

    def _run(self, settings: StreamStartIn, loop: asyncio.AbstractEventLoop) -> None:
        source: int | str = int(settings.source) if settings.source.isdigit() else settings.source
        camera, previous = cv2.VideoCapture(source), time.monotonic()
        if not camera.isOpened(): self.status.update({"running": False, "error": f"Unable to open source: {settings.source}"}); return
        try:
            while not self.stop_event.is_set():
                ok, frame = camera.read()
                if not ok: self.status.update({"running": False, "error": "Video source ended or frame capture failed"}); break
                detections = models.predict(frame, settings.model, settings.confidence)
                _, encoded = cv2.imencode(".jpg", annotate(frame, detections), [cv2.IMWRITE_JPEG_QUALITY, 82])
                with self.lock: self.latest_jpeg = encoded.tobytes()
                now = time.monotonic(); self.status["fps"] = round(1 / max(now - previous, .001), 1); previous = now
                event = {"source_id": settings.source_id, "detections": detections, "model": settings.model, "latitude": settings.latitude, "longitude": settings.longitude, "fps": self.status["fps"]}
                asyncio.run_coroutine_threadsafe(hub.publish("frame", event), loop)
                for incident in record_detections(frame, detections, settings):
                    asyncio.run_coroutine_threadsafe(hub.publish("incident", incident), loop)
                    if settings.auto_notify:
                        threading.Thread(target=notify_authorities, args=(incident["id"], settings.reporter_email), daemon=True).start()
                        threading.Thread(target=notify_zone_escalation, args=(incident["id"],), daemon=True).start()
        except Exception as exc: self.status.update({"running": False, "error": str(exc)})
        finally: camera.release(); self.status["running"] = False


stream = StreamWorker()


@asynccontextmanager
async def lifespan(_: FastAPI):
    for attempt in range(3):
        try:
            setup_database()
            break
        except psycopg.OperationalError as error:
            if attempt == 2:
                raise
            print(f"Supabase startup connection interrupted; retrying ({attempt + 1}/3): {error}")
            await asyncio.sleep(2 ** attempt)
    ensure_default_authority()
    models.load_available()
    yield
    stream.stop()


app = FastAPI(title="RoadSense AI Backend", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/media/{media_path:path}")
def get_media(media_path: str):
    content, mime_type = load_media(media_path)
    if content is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return Response(content=content, media_type=mime_type, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/health")
def health_check(): return {"status": "ok", "models": [name for name in MODELS if models.available(name)], "loaded_models": list(models.loaded), "stream": stream.status}


def authenticated_reporter_email(request: FastAPIRequest) -> str | None:
    session_id = request.cookies.get("roadsense_session")
    if not session_id:
        return None
    with connect_db() as db:
        row = db.execute("SELECT email FROM user_sessions WHERE id = ?", (session_id,)).fetchone()
    return row["email"] if row else None


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$", 2)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_session_response(email: str, name: str | None, gmail_connected: bool) -> JSONResponse:
    session_id = secrets.token_urlsafe(32)
    with connect_db() as db:
        db.execute("INSERT INTO user_sessions VALUES (?, ?, ?)", (session_id, email, utc_now()))
    response = JSONResponse({"email": email, "name": name, "gmail_connected": gmail_connected})
    response.set_cookie("roadsense_session", session_id, httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 24 * 30)
    return response


@app.post("/auth/sign-up/request", status_code=202)
def request_sign_up_verification(credentials: SignUpIn):
    email = normalized_email(credentials.email)
    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    with connect_db() as db:
        if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account already exists for this email")
        db.execute("DELETE FROM email_verifications WHERE email = ? OR expires_at < ?", (email, time.time()))
        db.execute("INSERT INTO email_verifications VALUES (?, ?, ?, ?, ?, ?)", (email, credentials.name.strip(), password_hash(credentials.password), code_hash, time.time() + 900, utc_now()))
    try:
        send_email(email, "Verify your RoadSense email", f"Your RoadSense verification code is:\n\n{code}\n\nEnter this code to finish creating your account. It expires in 15 minutes.")
    except Exception as error:
        with connect_db() as db:
            db.execute("DELETE FROM email_verifications WHERE email = ?", (email,))
        raise HTTPException(status_code=503, detail="Email verification is unavailable. Check the mail delivery configuration and try again.") from error
    return {"status": "verification_sent"}


@app.post("/auth/sign-up/confirm", status_code=201)
def confirm_sign_up_verification(payload: EmailVerificationIn):
    email = normalized_email(payload.email)
    code_hash = hashlib.sha256(payload.code.strip().encode()).hexdigest()
    with connect_db() as db:
        pending = db.execute("SELECT * FROM email_verifications WHERE email = ? AND expires_at > ?", (email, time.time())).fetchone()
        if pending is None or not hmac.compare_digest(code_hash, pending["code_hash"]):
            raise HTTPException(status_code=400, detail="That verification code is invalid or expired")
        if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account already exists for this email")
        db.execute("INSERT INTO users (email, display_name, password_hash, notify_email, created_at) VALUES (?, ?, ?, 1, ?)", (email, pending["display_name"], pending["password_hash"], utc_now()))
        db.execute("DELETE FROM email_verifications WHERE email = ?", (email,))
    return create_session_response(email, pending["display_name"], False)


@app.post("/auth/sign-in")
def sign_in(credentials: SignInIn):
    email = normalized_email(credentials.email)
    with connect_db() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        gmail = db.execute("SELECT display_name FROM google_accounts WHERE email = ?", (email,)).fetchone()
    if user is None or not password_matches(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return create_session_response(email, user["display_name"], gmail is not None)


@app.post("/auth/authority/sign-in")
def authority_sign_in(credentials: AuthoritySignInIn):
    """Shared authority portal credential kept solely in server environment settings."""
    expected_id = os.getenv("AUTHORITY_PORTAL_ID", "")
    expected_password = os.getenv("AUTHORITY_PORTAL_PASSWORD", "")
    authority_email = os.getenv("AUTHORITY_PORTAL_EMAIL", "").strip().lower()
    if not all((expected_id, expected_password, authority_email)):
        raise HTTPException(status_code=503, detail="Authority portal is not configured")
    if not (hmac.compare_digest(credentials.authority_id.strip(), expected_id) and hmac.compare_digest(credentials.password, expected_password)):
        raise HTTPException(status_code=401, detail="Authority ID or password is incorrect")
    with connect_db() as db:
        enabled = db.execute("SELECT name FROM authorities WHERE lower(email) = ? AND enabled = 1", (authority_email,)).fetchone()
    if enabled is None:
        raise HTTPException(status_code=503, detail="Configured authority portal email is not enabled")
    return create_session_response(authority_email, enabled["name"], False)


@app.post("/auth/password-reset/request")
def request_password_reset(payload: PasswordResetRequestIn):
    """Always return the same response so account emails cannot be enumerated."""
    email = payload.email.strip().lower()
    with connect_db() as db:
        user = db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            return {"status": "accepted"}
        code = f"{secrets.randbelow(1_000_000):06d}"
        token_hash = hashlib.sha256(code.encode()).hexdigest()
        db.execute("DELETE FROM password_resets WHERE email = ? OR expires_at < ?", (email, time.time()))
        db.execute("INSERT INTO password_resets VALUES (?, ?, ?, NULL)", (token_hash, email, time.time() + 1800))
    try:
        send_email(email, "Your RoadSense password reset code", f"Your RoadSense password reset code is:\n\n{code}\n\nEnter this code in the reset password screen. It expires in 30 minutes and can only be used once. If you did not request this, ignore this email.")
    except Exception:
        # Avoid leaking delivery configuration or account existence through this endpoint.
        pass
    return {"status": "accepted"}


@app.post("/auth/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetIn):
    email = payload.email.strip().lower()
    token_hash = hashlib.sha256(payload.code.strip().encode()).hexdigest()
    with connect_db() as db:
        reset = db.execute("SELECT email FROM password_resets WHERE token_hash = ? AND email = ? AND used_at IS NULL AND expires_at > ?", (token_hash, email, time.time())).fetchone()
        if reset is None:
            raise HTTPException(status_code=400, detail="This reset link is invalid or has expired")
        db.execute("UPDATE users SET password_hash = ? WHERE email = ?", (password_hash(payload.password), reset["email"]))
        db.execute("UPDATE password_resets SET used_at = ? WHERE token_hash = ?", (utc_now(), token_hash))
        db.execute("DELETE FROM user_sessions WHERE email = ?", (reset["email"],))
    return {"status": "password_reset"}


@app.post("/auth/password-reset/verify")
def verify_password_reset_code(payload: PasswordResetCodeIn):
    token_hash = hashlib.sha256(payload.code.strip().encode()).hexdigest()
    with connect_db() as db:
        reset = db.execute("SELECT 1 FROM password_resets WHERE token_hash = ? AND email = ? AND used_at IS NULL AND expires_at > ?", (token_hash, payload.email.strip().lower(), time.time())).fetchone()
    if reset is None:
        raise HTTPException(status_code=400, detail="This code is invalid or has expired")
    return {"status": "verified"}


@app.get("/auth/google/start")
def google_start(return_to: str = "http://127.0.0.1:3000/"):
    client_id, _, redirect_uri = google_config()
    candidate = urlsplit(return_to)
    candidate_origin = f"{candidate.scheme}://{candidate.netloc}"
    allowed_origins = {
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        os.getenv("ROADSENSE_APP_URL", "").strip().rstrip("/"),
        *[origin.strip().rstrip("/") for origin in os.getenv("CORS_ORIGINS", "").split(",")],
    }
    if candidate_origin not in allowed_origins:
        raise HTTPException(status_code=400, detail="Invalid application return URL")
    state = secrets.token_urlsafe(32)
    with connect_db() as db:
        db.execute("INSERT INTO oauth_states VALUES (?, ?, ?)", (state, return_to, utc_now()))
    params = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": "openid email profile https://www.googleapis.com/auth/gmail.send", "access_type": "offline", "prompt": "consent", "state": state}
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@app.get("/auth/google/callback")
def google_callback(code: str, state: str):
    with connect_db() as db:
        state_row = db.execute("SELECT return_to FROM oauth_states WHERE state = ?", (state,)).fetchone()
        db.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    if state_row is None:
        raise HTTPException(status_code=400, detail="Google authorization state has expired")
    client_id, secret, redirect_uri = google_config()
    tokens = google_request("https://oauth2.googleapis.com/token", data={"code": code, "client_id": client_id, "client_secret": secret, "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    profile = google_request("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    email, session_id = profile["email"], secrets.token_urlsafe(32)
    with connect_db() as db:
        db.execute("INSERT INTO google_accounts (email, access_token, refresh_token, expires_at, display_name, connected_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET access_token = excluded.access_token, refresh_token = COALESCE(excluded.refresh_token, google_accounts.refresh_token), expires_at = excluded.expires_at, display_name = excluded.display_name", (email, tokens["access_token"], tokens.get("refresh_token", ""), time.time() + int(tokens.get("expires_in", 3600)), profile.get("name"), utc_now()))
        db.execute("INSERT INTO user_sessions VALUES (?, ?, ?)", (session_id, email, utc_now()))
    response = RedirectResponse(f"{state_row['return_to']}?gmail=connected")
    response.set_cookie("roadsense_session", session_id, httponly=True, samesite="lax", secure=state_row["return_to"].startswith("https://"), max_age=60 * 60 * 24 * 30)
    return response


@app.get("/auth/me")
def current_user(request: FastAPIRequest):
    email = authenticated_reporter_email(request)
    if not email:
        return {"email": None, "name": None, "gmail_connected": False}
    with connect_db() as db:
        account = db.execute("SELECT display_name FROM google_accounts WHERE email = ?", (email,)).fetchone()
        user = db.execute("SELECT display_name, notify_email FROM users WHERE email = ?", (email,)).fetchone()
        incident_count = dict(db.execute("SELECT COUNT(*) AS count FROM incidents WHERE reporter_email = ?", (email,)).fetchone())["count"]
    return {"email": email, "name": account["display_name"] if account else (user["display_name"] if user else None), "gmail_connected": account is not None, "notify_email": bool(user["notify_email"]) if user else True, "incident_count": incident_count, "password_account": user is not None}


@app.patch("/auth/profile")
def update_profile(update: ProfileUpdateIn, request: FastAPIRequest):
    email = authenticated_reporter_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Sign in to update your profile")
    with connect_db() as db:
        if db.execute("UPDATE users SET display_name = ?, notify_email = ? WHERE email = ?", (update.name.strip(), int(update.notify_email), email)).rowcount == 0:
            raise HTTPException(status_code=400, detail="Profile changes are available for email-and-password accounts")
    return current_user(request)


@app.post("/auth/change-password")
def change_password(change: PasswordChangeIn, request: FastAPIRequest):
    email = authenticated_reporter_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Sign in to change your password")
    with connect_db() as db:
        user = db.execute("SELECT password_hash FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not password_matches(change.current_password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Current password is incorrect")
        db.execute("UPDATE users SET password_hash = ? WHERE email = ?", (password_hash(change.new_password), email))
    return {"status": "password_changed"}


@app.post("/auth/sign-out")
def sign_out(request: FastAPIRequest):
    session_id = request.cookies.get("roadsense_session")
    if session_id:
        with connect_db() as db:
            db.execute("DELETE FROM user_sessions WHERE id = ?", (session_id,))
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie("roadsense_session", samesite="lax")
    return response

@app.get("/models")
def list_models(): return [{"name": name, "available": models.available(name), "loaded": name in models.loaded, "path": str(path)} for name, path in MODELS.items()]

@app.post("/predict")
async def predict(file: UploadFile = File(...), model: str = Query(DEFAULT_MODEL, min_length=1, max_length=80), confidence: float = Query(0.35, ge=0.05, le=0.95)):
    if not models.available(model): raise HTTPException(status_code=503, detail=f"Model '{model}' is unavailable")
    image = cv2.imdecode(np.frombuffer(await file.read(), np.uint8), cv2.IMREAD_COLOR)
    if image is None: raise HTTPException(status_code=422, detail="Upload must be a valid image")
    detections = models.predict(image, model, confidence)
    return {"model": model, "detections": detections, "count": len(detections)}


@app.post("/streams/browser-frame")
async def process_browser_frame(
    background_tasks: BackgroundTasks,
    request: FastAPIRequest,
    file: UploadFile = File(...),
    model: str = Query(DEFAULT_MODEL, min_length=1, max_length=80),
    confidence: float = Query(0.20, ge=0.05, le=0.95),
    source_id: str = Query("browser-camera", min_length=1, max_length=80),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
):
    """Analyze a browser camera frame and create deduplicated live incidents."""
    if not models.available(model):
        raise HTTPException(status_code=503, detail=f"Model '{model}' is unavailable")
    image = cv2.imdecode(np.frombuffer(await file.read(), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="Camera frame must be a valid image")
    settings = StreamStartIn(source="browser", source_id=source_id, model=model, confidence=confidence, latitude=latitude, longitude=longitude, reporter_email=authenticated_reporter_email(request))
    detections = models.predict(image, model, confidence)
    incidents = record_detections(image, detections, settings)
    for incident in incidents:
        await hub.publish("incident", incident)
        background_tasks.add_task(notify_authorities, incident["id"], settings.reporter_email)
    return {"model": model, "detections": detections, "count": len(detections), "incidents": incidents, "frame_width": image.shape[1], "frame_height": image.shape[0]}

@app.post("/locations", status_code=201)
async def create_location(location: LocationIn):
    record = location.model_dump(); record["captured_at"] = (record["captured_at"] or datetime.now(timezone.utc)).isoformat()
    with connect_db() as db:
        values = (record["source_id"], record["captured_at"], record["latitude"], record["longitude"], record["accuracy_m"], record["heading"], record["speed_kph"])
        if isinstance(db, PostgresDatabase):
            record["id"] = db.execute("INSERT INTO locations (source_id, captured_at, latitude, longitude, accuracy_m, heading, speed_kph) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id", values).fetchone()["id"]
        else:
            record["id"] = db.execute("INSERT INTO locations (source_id, captured_at, latitude, longitude, accuracy_m, heading, speed_kph) VALUES (?, ?, ?, ?, ?, ?, ?)", values).lastrowid
    await hub.publish("location", record); return record

@app.get("/locations/latest")
def latest_locations():
    with connect_db() as db: rows = db.execute("SELECT l.* FROM locations l INNER JOIN (SELECT source_id, MAX(captured_at) captured_at FROM locations GROUP BY source_id) latest ON l.source_id = latest.source_id AND l.captured_at = latest.captured_at ORDER BY l.captured_at DESC").fetchall()
    return [dict(row) for row in rows]

@app.get("/locations/{source_id}/history")
def location_history(source_id: str, limit: int = Query(200, ge=1, le=2000)):
    with connect_db() as db: rows = db.execute("SELECT * FROM locations WHERE source_id = ? ORDER BY captured_at DESC LIMIT ?", (source_id, limit)).fetchall()
    return [dict(row) for row in rows]

@app.get("/incidents")
def list_incidents(status: str | None = None, limit: int = Query(100, ge=1, le=1000)):
    query = "SELECT * FROM incidents"
    parameters: tuple[object, ...] = (limit,)
    if status is not None:
        query += " WHERE status = ?"
        parameters = (status, limit)
    query += " ORDER BY created_at DESC LIMIT ?"
    with connect_db() as db:
        rows = db.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


@app.get("/zones")
def list_incident_zones():
    """Return live report-density zones for public and authority maps."""
    with connect_db() as db:
        return incident_zones(db)

@app.delete("/incidents")
async def clear_incident_history():
    """Remove locally stored incident records and their uploaded evidence."""
    with connect_db() as db:
        evidence = [dict(row)["image_path"] for row in db.execute("SELECT image_path FROM incidents WHERE image_path IS NOT NULL").fetchall()]
        count = dict(db.execute("SELECT COUNT(*) AS count FROM incidents").fetchone())["count"]
        db.execute("DELETE FROM notifications")
        db.execute("DELETE FROM sms_reports")
        db.execute("DELETE FROM zone_alerts")
        db.execute("DELETE FROM incidents")
    for filename in evidence:
        delete_media(filename)
    await hub.publish("incident_history_cleared", {"count": count})
    return {"status": "cleared", "count": count}


@app.get("/sms/reporting")
def sms_reporting_status():
    """Public configuration the dashboard can use to show the reporting number."""
    number = os.getenv("TWILIO_REPORTING_NUMBER", "").strip()
    return {"enabled": bool(number and os.getenv("TWILIO_AUTH_TOKEN")), "number": number or None}


@app.post("/media/photo-location")
async def inspect_photo_location(photo: UploadFile = File(...)):
    """Inspect an original image before reporting, without storing it."""
    content_type = (photo.content_type or "").lower()
    if not content_type.startswith("image/"):
        return {"found": False, "reason": "Only original image files can contain photo GPS."}
    coordinates = extract_photo_gps(await photo.read())
    if coordinates is None:
        return {"found": False, "reason": "No embedded GPS was found. Screenshots, edited copies, and social-media downloads often remove it."}
    return {"found": True, "latitude": coordinates[0], "longitude": coordinates[1], "source": "photo_metadata"}


@app.post("/webhooks/twilio/sms")
async def receive_sms_report(request: FastAPIRequest, background_tasks: BackgroundTasks):
    """Turn a signed Twilio inbound SMS into a RoadSense incident and authority email."""
    form_data = await request.form()
    form = {key: str(value) for key, value in form_data.items()}
    if not os.getenv("TWILIO_AUTH_TOKEN"):
        raise HTTPException(status_code=503, detail="Inbound SMS is not configured")
    if not valid_twilio_request(str(request.url), form, request.headers.get("X-Twilio-Signature")):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    sender = form.get("From", "").strip()
    message = form.get("Body", "").strip()
    message_sid = form.get("MessageSid", "").strip()
    if not sender or not message or not message_sid:
        raise HTTPException(status_code=422, detail="Twilio message is missing sender, body, or ID")

    try:
        english_message = translate_sms_to_english(message)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    hazard, location, details = sms_report_parts(english_message)
    now, incident_id = utc_now(), str(uuid.uuid4())
    with connect_db() as db:
        existing = db.execute("SELECT incident_id FROM sms_reports WHERE message_sid = ?", (message_sid,)).fetchone()
        if existing is not None:
            return Response("<Response><Message>RoadSense already received this report.</Message></Response>", media_type="application/xml")
        db.execute("INSERT INTO incidents (id, created_at, updated_at, source_id, model_name, hazard_type, confidence, latitude, longitude, accuracy_m, status, details, image_path, detection_count, reporter_name, reporter_email, location_name, address_line, area, city, postal_code, landmark, location_source) VALUES (?, ?, ?, 'sms-report', 'sms-report', ?, 1.0, NULL, NULL, NULL, 'open', ?, NULL, 1, ?, NULL, ?, NULL, NULL, NULL, NULL, NULL, 'sms_sender')", (incident_id, now, now, hazard, details, f"SMS reporter {sender}", location))
        db.execute("INSERT INTO sms_reports (message_sid, incident_id, sender_phone, received_at, original_body, english_body) VALUES (?, ?, ?, ?, ?, ?)", (message_sid, incident_id, sender, now, message, english_message))
        incident = incident_by_id(db, incident_id)
    await hub.publish("incident", incident)
    background_tasks.add_task(notify_authorities, incident_id)
    background_tasks.add_task(notify_zone_escalation, incident_id)
    return Response("<Response><Message>RoadSense received your report. Thank you.</Message></Response>", media_type="application/xml")

@app.post("/incidents", status_code=201)
async def report_incident(report: IncidentReportIn, background_tasks: BackgroundTasks, request: FastAPIRequest):
    incident_id, now = str(uuid.uuid4()), utc_now()
    with connect_db() as db:
        db.execute("INSERT INTO incidents (id, created_at, updated_at, source_id, model_name, hazard_type, confidence, latitude, longitude, accuracy_m, status, details, image_path, detection_count, reporter_name, reporter_email, location_name, address_line, area, city, postal_code, landmark) VALUES (?, ?, ?, ?, 'manual-report', ?, 1.0, ?, ?, NULL, 'open', ?, NULL, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (incident_id, now, now, report.source_id, report.hazard_type, report.latitude, report.longitude, report.details, report.reporter_name, report.reporter_email, report.location_name, report.address_line, report.area, report.city, report.postal_code, report.landmark))
        incident = incident_by_id(db, incident_id)
    await hub.publish("incident", incident)
    background_tasks.add_task(notify_authorities, incident_id, authenticated_reporter_email(request))
    background_tasks.add_task(notify_zone_escalation, incident_id)
    return incident

@app.post("/incidents/report", status_code=201)
async def report_incident_with_photo(
    background_tasks: BackgroundTasks,
    request: FastAPIRequest,
    hazard_type: str = Form(..., min_length=1, max_length=80),
    reporter_name: str = Form(..., min_length=1, max_length=120),
    reporter_email: str | None = Form(default=None, max_length=254),
    location_name: str = Form(..., min_length=1, max_length=240),
    address_line: str | None = Form(default=None, max_length=240),
    area: str | None = Form(default=None, max_length=120),
    city: str | None = Form(default=None, max_length=120),
    postal_code: str | None = Form(default=None, max_length=20),
    landmark: str | None = Form(default=None, max_length=240),
    latitude: float | None = Form(default=None, ge=-90, le=90),
    longitude: float | None = Form(default=None, ge=-180, le=180),
    location_source: Literal["manual_pin"] | None = Form(default=None),
    details: str | None = Form(default=None, max_length=4000),
    photo: UploadFile | None = File(default=None),
):
    incident_id, now, image_name = str(uuid.uuid4()), utc_now(), None
    model_name, model_confidence, detection_count = "manual-report", 1.0, 1
    location_source = location_source if latitude is not None and longitude is not None and location_source == "manual_pin" else ("reporter_device" if latitude is not None and longitude is not None else "not_supplied")
    if photo and photo.filename:
        allowed_evidence = {
            "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
            "image/heic": ".heic", "image/heif": ".heif",
            "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
        }
        extension_types = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
            ".heic": "image/heic", ".heif": "image/heif", ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
        }
        content_type = (photo.content_type or "").lower()
        if content_type not in allowed_evidence:
            content_type = extension_types.get(Path(photo.filename).suffix.lower(), content_type)
        if content_type not in allowed_evidence:
            raise HTTPException(status_code=415, detail="Evidence must be a JPEG, PNG, WebP, HEIC, HEIF, MP4, WebM, or MOV file")
        suffix = allowed_evidence[content_type]
        image_name = f"{incident_id}{suffix}"
        content = await photo.read()
        limit_mb = 50 if content_type.startswith("video/") else 10
        if len(content) > limit_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{'Video' if photo.content_type.startswith('video/') else 'Photo'} must be {limit_mb} MB or smaller")
        store_media(image_name, content, content_type)
        if content_type.startswith("image/"):
            if not models.available(DEFAULT_MODEL):
                raise HTTPException(status_code=503, detail=f"Detection model '{DEFAULT_MODEL}' is unavailable")
            try:
                with Image.open(BytesIO(content)) as uploaded_image:
                    rgb_image = np.asarray(uploaded_image.convert("RGB"))
                detections = models.predict(cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR), DEFAULT_MODEL, 0.20)
            except Exception as error:
                raise HTTPException(status_code=422, detail=f"The uploaded image could not be analyzed: {error}") from error
            model_name = DEFAULT_MODEL
            detection_count = len(detections)
            if detections:
                strongest = max(detections, key=lambda detection: detection["confidence"])
                hazard_type = strongest["class"]
                model_confidence = strongest["confidence"]
            else:
                model_confidence = 0.0
            photo_gps = extract_photo_gps(content)
            if photo_gps is not None:
                latitude, longitude = photo_gps
                location_source = "photo_metadata"
    with connect_db() as db:
        db.execute("INSERT INTO incidents (id, created_at, updated_at, source_id, model_name, hazard_type, confidence, latitude, longitude, accuracy_m, status, details, image_path, detection_count, reporter_name, reporter_email, location_name, address_line, area, city, postal_code, landmark, location_source) VALUES (?, ?, ?, 'citizen-report', ?, ?, ?, ?, ?, NULL, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (incident_id, now, now, model_name, hazard_type, model_confidence, latitude, longitude, details, image_name, detection_count, reporter_name, reporter_email, location_name, address_line, area, city, postal_code, landmark, location_source))
        incident = incident_by_id(db, incident_id)
    await hub.publish("incident", incident)
    background_tasks.add_task(notify_authorities, incident_id, authenticated_reporter_email(request))
    background_tasks.add_task(notify_zone_escalation, incident_id)
    return incident

@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    with connect_db() as db:
        incident = incident_by_id(db, incident_id); incident["notifications"] = [dict(row) for row in db.execute("SELECT * FROM notifications WHERE incident_id = ? ORDER BY sent_at DESC", (incident_id,))]; incident["resolution_proofs"] = [dict(row) for row in db.execute("SELECT * FROM resolution_proofs WHERE incident_id = ? ORDER BY created_at DESC", (incident_id,))]; incident["authority_updates"] = [dict(row) for row in db.execute("SELECT * FROM authority_updates WHERE incident_id = ? ORDER BY created_at DESC", (incident_id,))]
    return incident


@app.get("/authority/incidents")
def authority_incidents(request: FastAPIRequest, status: str | None = None):
    require_authority(request)
    query = "SELECT * FROM incidents"
    parameters: tuple[object, ...] = ()
    if status is not None:
        query += " WHERE status = ?"
        parameters = (status,)
    query += " ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END, created_at DESC"
    with connect_db() as db:
        rows = db.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


@app.post("/authority/incidents/{incident_id}/update")
async def post_authority_update(incident_id: str, update: AuthorityWorkUpdateIn, request: FastAPIRequest):
    authority_email = require_authority(request)
    now = utc_now()
    with connect_db() as db:
        incident_by_id(db, incident_id)
        db.execute("INSERT INTO authority_updates VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), incident_id, authority_email, update.message.strip(), update.status, now))
        db.execute("UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?", (update.status, now, incident_id))
        incident = incident_by_id(db, incident_id)
    await hub.publish("incident_updated", incident)
    return incident


@app.post("/authority/incidents/{incident_id}/proof", status_code=201)
async def submit_resolution_proof(
    incident_id: str,
    request: FastAPIRequest,
    note: str = Form(..., min_length=4, max_length=4000),
    proof: UploadFile | None = File(default=None),
):
    authority_email = require_authority(request)
    proof_id, now, media_path = str(uuid.uuid4()), utc_now(), None
    if proof and proof.filename:
        allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}
        content_type = (proof.content_type or "").lower()
        suffix = allowed.get(content_type, Path(proof.filename).suffix.lower())
        if suffix not in allowed.values():
            raise HTTPException(status_code=415, detail="Proof must be a JPEG, PNG, WebP, MP4, WebM, or MOV file")
        content = await proof.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Proof must be 50 MB or smaller")
        media_path = f"proof-{proof_id}{suffix}"
        store_media(media_path, content, content_type)
    with connect_db() as db:
        incident_by_id(db, incident_id)
        db.execute("INSERT INTO resolution_proofs VALUES (?, ?, ?, ?, ?, ?)", (proof_id, incident_id, authority_email, note.strip(), media_path, now))
        db.execute("INSERT INTO authority_updates VALUES (?, ?, ?, ?, 'resolved', ?)", (str(uuid.uuid4()), incident_id, authority_email, note.strip(), now))
        db.execute("UPDATE incidents SET status = 'resolved', updated_at = ? WHERE id = ?", (now, incident_id))
        incident = incident_by_id(db, incident_id)
    await hub.publish("incident_updated", incident)
    return {"id": proof_id, "incident": incident, "authority_email": authority_email, "note": note.strip(), "media_path": media_path, "created_at": now}

@app.patch("/incidents/{incident_id}")
async def update_incident(incident_id: str, update: IncidentUpdateIn):
    if update.status is None and update.details is None:
        raise HTTPException(status_code=422, detail="Provide a status and/or details")
    with connect_db() as db:
        if db.execute("UPDATE incidents SET status = COALESCE(?, status), details = COALESCE(?, details), updated_at = ? WHERE id = ?", (update.status, update.details, utc_now(), incident_id)).rowcount == 0: raise HTTPException(status_code=404, detail="Incident not found")
        incident = incident_by_id(db, incident_id)
    await hub.publish("incident_updated", incident); return incident

@app.get("/authorities")
def list_authorities():
    with connect_db() as db: return [dict(row) for row in db.execute("SELECT * FROM authorities ORDER BY name").fetchall()]

@app.post("/authorities", status_code=201)
def create_authority(authority: AuthorityIn):
    record = authority.model_dump() | {"id": str(uuid.uuid4()), "created_at": utc_now()}
    with connect_db() as db: db.execute("INSERT INTO authorities (id, name, jurisdiction, email, phone, whatsapp_enabled, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (record["id"], record["name"], record["jurisdiction"], record["email"], record["phone"], int(record["whatsapp_enabled"]), int(record["enabled"]), record["created_at"]))
    return record

@app.post("/incidents/{incident_id}/notify")
def notify_incident(incident_id: str, background_tasks: BackgroundTasks, asynchronous: bool = True):
    with connect_db() as db: incident_by_id(db, incident_id)
    if asynchronous: background_tasks.add_task(notify_authorities, incident_id); return {"status": "queued", "incident_id": incident_id}
    return {"status": "complete", "incident_id": incident_id, "outcomes": notify_authorities(incident_id)}

@app.post("/streams/start")
async def start_stream(settings: StreamStartIn, request: FastAPIRequest):
    if not models.available(settings.model): raise HTTPException(status_code=503, detail=f"Model '{settings.model}' is unavailable")
    settings.reporter_email = authenticated_reporter_email(request)
    stream.start(settings, asyncio.get_running_loop()); return {"status": "starting", **stream.status}

@app.post("/streams/stop")
def stop_stream(): stream.stop(); return {"status": "stopped"}

@app.get("/streams/status")
def stream_status(): return stream.status

@app.get("/streams/mjpeg")
def mjpeg_stream():
    def frames():
        while stream.status.get("running"):
            with stream.lock: frame = stream.latest_jpeg
            if frame: yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(.05)
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws/live")
async def live_events(websocket: WebSocket):
    await hub.connect(websocket)
    try:
        await websocket.send_json({"event": "connected", "data": {"stream": stream.status}, "sent_at": utc_now()})
        while True: await websocket.receive_text()
    except WebSocketDisconnect: hub.disconnect(websocket)


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

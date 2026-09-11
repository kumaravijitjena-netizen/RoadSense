"""RoadSense detection, incident, location, and notification service."""

import asyncio
import base64
import json
import os
import secrets
import smtplib
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import cv2
import numpy as np
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request as FastAPIRequest, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
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
DATA_DIR = Path(os.getenv("ROADSENSE_DATA_DIR", Path(__file__).resolve().parent / "data"))
MEDIA_DIR, DB_PATH = DATA_DIR / "media", DATA_DIR / "roadsense.db"
FRONTEND_DIST = BASE_DIR / "road_sense_web" / "roadsense_frontend" / "dist" / "public"
MODELS = {"v1": BASE_DIR / "runs" / "pothole_manhole_v1" / "weights" / "best.pt", "v2": BASE_DIR / "runs" / "pothole_manhole_v2_augmented" / "weights" / "best.pt"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def setup_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, source_id TEXT NOT NULL, model_name TEXT NOT NULL, hazard_type TEXT NOT NULL, confidence REAL NOT NULL, latitude REAL, longitude REAL, accuracy_m REAL, status TEXT NOT NULL DEFAULT 'open', details TEXT, image_path TEXT, detection_count INTEGER NOT NULL, reporter_name TEXT, reporter_email TEXT, location_name TEXT);
        CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL, captured_at TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL, accuracy_m REAL, heading REAL, speed_kph REAL);
        CREATE TABLE IF NOT EXISTS authorities (id TEXT PRIMARY KEY, name TEXT NOT NULL, jurisdiction TEXT, email TEXT, phone TEXT, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, authority_id TEXT NOT NULL, channel TEXT NOT NULL, status TEXT NOT NULL, detail TEXT, sent_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS oauth_states (state TEXT PRIMARY KEY, return_to TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS google_accounts (email TEXT PRIMARY KEY, access_token TEXT NOT NULL, refresh_token TEXT NOT NULL, expires_at REAL NOT NULL, display_name TEXT, connected_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS user_sessions (id TEXT PRIMARY KEY, email TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS incidents_created_at ON incidents(created_at DESC);
        CREATE INDEX IF NOT EXISTS locations_source_time ON locations(source_id, captured_at DESC);
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(incidents)")}
        for name, definition in (("details", "TEXT"), ("reporter_name", "TEXT"), ("reporter_email", "TEXT"), ("location_name", "TEXT")):
            if name not in columns:
                db.execute(f"ALTER TABLE incidents ADD COLUMN {name} {definition}")


class AuthorityIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    jurisdiction: str | None = Field(default=None, max_length=160)
    email: str | None = None
    phone: str | None = None
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
    model: Literal["v1", "v2"] = "v2"
    confidence: float = Field(default=0.35, ge=0.05, le=0.95)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    auto_notify: bool = True
    reporter_email: str | None = None


class IncidentUpdateIn(BaseModel):
    status: Literal["open", "acknowledged", "resolved", "false_positive"] | None = None
    details: str | None = Field(default=None, max_length=4000)


class IncidentReportIn(BaseModel):
    hazard_type: Literal["pothole", "manhole", "other"]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source_id: str = Field(default="citizen-report", min_length=1, max_length=80)
    reporter_name: str = Field(min_length=1, max_length=120)
    reporter_email: str | None = Field(default=None, max_length=254)
    location_name: str = Field(min_length=1, max_length=240)
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

    def predict(self, image: np.ndarray, model_name: str, confidence: float) -> list[dict]:
        model = self.loaded.get(model_name)
        if model is None:
            raise RuntimeError(f"Model '{model_name}' is unavailable")
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


def incident_by_id(db: sqlite3.Connection, incident_id: str) -> dict:
    row = db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return dict(row)


def record_detections(frame: np.ndarray, detections: list[dict], settings: StreamStartIn) -> list[dict]:
    created = []
    with connect_db() as db:
        for detection in detections:
            duplicate = db.execute("SELECT 1 FROM incidents WHERE source_id = ? AND hazard_type = ? AND julianday(created_at) > julianday('now', '-30 seconds') LIMIT 1", (settings.source_id, detection["class"])).fetchone()
            if duplicate:
                continue
            incident_id, now = str(uuid.uuid4()), utc_now()
            image_name = f"{incident_id}.jpg"
            cv2.imwrite(str(MEDIA_DIR / image_name), annotate(frame, [detection]))
            db.execute("INSERT INTO incidents (id, created_at, updated_at, source_id, model_name, hazard_type, confidence, latitude, longitude, accuracy_m, status, details, image_path, detection_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'open', NULL, ?, 1)", (incident_id, now, now, settings.source_id, settings.model, detection["class"], detection["confidence"], settings.latitude, settings.longitude, image_name))
            created.append(incident_by_id(db, incident_id))
    return created


def notification_text(incident: dict) -> tuple[str, str]:
    coordinates = "Location not supplied" if incident["latitude"] is None else f"{incident['latitude']:.6f}, {incident['longitude']:.6f}"
    location = incident.get("location_name") or coordinates
    subject = f"RoadSense alert: {incident['hazard_type']} detected"
    reporter = f"\nReported by: {incident['reporter_name']} ({incident['reporter_email'] or 'email not provided'})" if incident.get("reporter_name") else ""
    return subject, f"RoadSense detected a {incident['hazard_type']} ({incident['confidence']:.0%} confidence).\nSource: {incident['source_id']}\nLocation: {location}\nCoordinates: {coordinates}{reporter}\nDetected at: {incident['created_at']}\nIncident ID: {incident['id']}"


def send_email(recipient: str, subject: str, body: str) -> str:
    host, sender = os.getenv("SMTP_HOST"), os.getenv("SMTP_FROM")
    if not host or not sender:
        raise RuntimeError("SMTP is not configured")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, recipient, subject
    message.set_content(body)
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as client:
        if os.getenv("SMTP_TLS", "true").lower() == "true": client.starttls()
        if os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD"): client.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        client.send_message(message)
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


def send_gmail(email: str, recipient: str, subject: str, body: str) -> str:
    message = EmailMessage(); message["From"], message["To"], message["Subject"] = email, recipient, subject; message.set_content(body)
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


def notify_authorities(incident_id: str, reporter_email: str | None = None) -> list[dict]:
    outcomes = []
    with connect_db() as db:
        incident, contacts = incident_by_id(db, incident_id), db.execute("SELECT * FROM authorities WHERE enabled = 1").fetchall()
        subject, body = notification_text(incident)
        for authority in map(dict, contacts):
            for channel, recipient, sender in (("email", authority["email"], lambda: send_gmail(reporter_email, authority["email"], subject, body) if reporter_email else send_email(authority["email"], subject, body)), ("sms", authority["phone"], lambda: send_sms(authority["phone"], body))):
                if not recipient: continue
                try: detail, status = sender(), "sent"
                except Exception as exc: detail, status = str(exc), "failed"
                outcomes.append({"authority": authority["name"], "channel": channel, "status": status, "detail": detail})
                db.execute("INSERT INTO notifications VALUES (?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), incident_id, authority["id"], channel, status, detail, utc_now()))
    return outcomes


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
                    if settings.auto_notify: threading.Thread(target=notify_authorities, args=(incident["id"], settings.reporter_email), daemon=True).start()
        except Exception as exc: self.status.update({"running": False, "error": str(exc)})
        finally: camera.release(); self.status["running"] = False


stream = StreamWorker()


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_database(); models.load_available()
    yield
    stream.stop()


app = FastAPI(title="RoadSense AI Backend", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=MEDIA_DIR, check_dir=False), name="media")


@app.get("/health")
def health_check(): return {"status": "ok", "models": list(models.loaded), "stream": stream.status}


def authenticated_reporter_email(request: FastAPIRequest) -> str | None:
    session_id = request.cookies.get("roadsense_session")
    if not session_id:
        return None
    with connect_db() as db:
        row = db.execute("SELECT email FROM user_sessions WHERE id = ?", (session_id,)).fetchone()
    return row["email"] if row else None


@app.get("/auth/google/start")
def google_start(return_to: str = "http://127.0.0.1:3000/"):
    client_id, _, redirect_uri = google_config()
    if not return_to.startswith(("http://127.0.0.1:3000", "http://localhost:3000")):
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
    response.set_cookie("roadsense_session", session_id, httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 24 * 30)
    return response


@app.get("/auth/me")
def current_user(request: FastAPIRequest):
    email = authenticated_reporter_email(request)
    return {"email": email, "gmail_connected": email is not None}

@app.get("/models")
def list_models(): return [{"name": name, "available": name in models.loaded, "path": str(path)} for name, path in MODELS.items()]

@app.post("/predict")
async def predict(file: UploadFile = File(...), model: Literal["v1", "v2"] = "v2", confidence: float = Query(0.35, ge=0.05, le=0.95)):
    if model not in models.loaded: raise HTTPException(status_code=503, detail=f"Model '{model}' is unavailable")
    image = cv2.imdecode(np.frombuffer(await file.read(), np.uint8), cv2.IMREAD_COLOR)
    if image is None: raise HTTPException(status_code=422, detail="Upload must be a valid image")
    detections = models.predict(image, model, confidence)
    return {"model": model, "detections": detections, "count": len(detections)}


@app.post("/streams/browser-frame")
async def process_browser_frame(
    background_tasks: BackgroundTasks,
    request: FastAPIRequest,
    file: UploadFile = File(...),
    model: Literal["v1", "v2"] = "v2",
    confidence: float = Query(0.35, ge=0.05, le=0.95),
    source_id: str = Query("browser-camera", min_length=1, max_length=80),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
):
    """Analyze a browser camera frame and create deduplicated live incidents."""
    if model not in models.loaded:
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
        record["id"] = db.execute("INSERT INTO locations (source_id, captured_at, latitude, longitude, accuracy_m, heading, speed_kph) VALUES (?, ?, ?, ?, ?, ?, ?)", (record["source_id"], record["captured_at"], record["latitude"], record["longitude"], record["accuracy_m"], record["heading"], record["speed_kph"])).lastrowid
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
    with connect_db() as db: rows = db.execute("SELECT * FROM incidents WHERE (? IS NULL OR status = ?) ORDER BY created_at DESC LIMIT ?", (status, status, limit)).fetchall()
    return [dict(row) for row in rows]

@app.post("/incidents", status_code=201)
async def report_incident(report: IncidentReportIn, background_tasks: BackgroundTasks, request: FastAPIRequest):
    incident_id, now = str(uuid.uuid4()), utc_now()
    with connect_db() as db:
        db.execute("INSERT INTO incidents (id, created_at, updated_at, source_id, model_name, hazard_type, confidence, latitude, longitude, accuracy_m, status, details, image_path, detection_count, reporter_name, reporter_email, location_name) VALUES (?, ?, ?, ?, 'manual-report', ?, 1.0, ?, ?, NULL, 'open', ?, NULL, 1, ?, ?, ?)",
                   (incident_id, now, now, report.source_id, report.hazard_type, report.latitude, report.longitude, report.details, report.reporter_name, report.reporter_email, report.location_name))
        incident = incident_by_id(db, incident_id)
    await hub.publish("incident", incident)
    background_tasks.add_task(notify_authorities, incident_id, authenticated_reporter_email(request))
    return incident

@app.post("/incidents/report", status_code=201)
async def report_incident_with_photo(
    background_tasks: BackgroundTasks,
    request: FastAPIRequest,
    hazard_type: Literal["pothole", "manhole", "other"] = Form(...),
    reporter_name: str = Form(..., min_length=1, max_length=120),
    reporter_email: str | None = Form(default=None, max_length=254),
    location_name: str = Form(..., min_length=1, max_length=240),
    latitude: float | None = Form(default=None, ge=-90, le=90),
    longitude: float | None = Form(default=None, ge=-180, le=180),
    details: str | None = Form(default=None, max_length=4000),
    photo: UploadFile | None = File(default=None),
):
    incident_id, now, image_name = str(uuid.uuid4()), utc_now(), None
    if photo and photo.filename:
        allowed_evidence = {
            "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
            "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
        }
        if photo.content_type not in allowed_evidence:
            raise HTTPException(status_code=415, detail="Evidence must be a JPEG, PNG, WebP, MP4, WebM, or MOV file")
        suffix = allowed_evidence[photo.content_type]
        image_name = f"{incident_id}{suffix}"
        content = await photo.read()
        limit_mb = 50 if photo.content_type.startswith("video/") else 10
        if len(content) > limit_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{'Video' if photo.content_type.startswith('video/') else 'Photo'} must be {limit_mb} MB or smaller")
        (MEDIA_DIR / image_name).write_bytes(content)
    with connect_db() as db:
        db.execute("INSERT INTO incidents (id, created_at, updated_at, source_id, model_name, hazard_type, confidence, latitude, longitude, accuracy_m, status, details, image_path, detection_count, reporter_name, reporter_email, location_name) VALUES (?, ?, ?, 'citizen-report', 'manual-report', ?, 1.0, ?, ?, NULL, 'open', ?, ?, 1, ?, ?, ?)",
                   (incident_id, now, now, hazard_type, latitude, longitude, details, image_name, reporter_name, reporter_email, location_name))
        incident = incident_by_id(db, incident_id)
    await hub.publish("incident", incident)
    background_tasks.add_task(notify_authorities, incident_id, authenticated_reporter_email(request))
    return incident

@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    with connect_db() as db:
        incident = incident_by_id(db, incident_id); incident["notifications"] = [dict(row) for row in db.execute("SELECT * FROM notifications WHERE incident_id = ? ORDER BY sent_at DESC", (incident_id,))]
    return incident

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
    with connect_db() as db: db.execute("INSERT INTO authorities VALUES (?, ?, ?, ?, ?, ?, ?)", (record["id"], record["name"], record["jurisdiction"], record["email"], record["phone"], int(record["enabled"]), record["created_at"]))
    return record

@app.post("/incidents/{incident_id}/notify")
def notify_incident(incident_id: str, background_tasks: BackgroundTasks, asynchronous: bool = True):
    with connect_db() as db: incident_by_id(db, incident_id)
    if asynchronous: background_tasks.add_task(notify_authorities, incident_id); return {"status": "queued", "incident_id": incident_id}
    return {"status": "complete", "incident_id": incident_id, "outcomes": notify_authorities(incident_id)}

@app.post("/streams/start")
async def start_stream(settings: StreamStartIn, request: FastAPIRequest):
    if settings.model not in models.loaded: raise HTTPException(status_code=503, detail=f"Model '{settings.model}' is unavailable")
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

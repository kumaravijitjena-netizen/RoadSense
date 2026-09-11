# RoadSense backend

FastAPI service for the trained RoadSense YOLO models. It supports image prediction, real-time camera/RTSP/video processing, MJPEG and WebSocket live updates, incident history, location history, and configurable authority notifications.

## Start

From `road_sense_web/backend`:

```powershell
..\..\venv\Scripts\python.exe -m pip install -r requirements.txt
..\..\venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs` for the interactive API. The service finds the V1 and V2 weights in `runs/`; V2 is the default.

## Live feed

Start a local camera feed with `POST /streams/start`:

```json
{"source":"0","source_id":"vehicle-12","model":"v2","confidence":0.35,"latitude":12.9716,"longitude":77.5946}
```

`source` can also be a video file path or RTSP URL. View the annotated stream at `/streams/mjpeg` and subscribe to `ws://localhost:8000/ws/live` for `frame`, `incident`, `location`, and `incident_updated` events.

`POST /locations` accepts GPS updates. `GET /locations/latest` gives map markers, `GET /locations/{source_id}/history` returns route history, and `GET /incidents` is the history feed. Saved incident evidence is served from `/media/`.

Add field notes or a resolution note to an existing incident with `PATCH /incidents/{incident_id}`:

```json
{"status":"resolved","details":"Maintenance crew repaired the pothole on 10 September."}
```

## Notifications

Create recipients with `POST /authorities`. Every incident submitted through `POST /incidents` or `POST /incidents/report` automatically queues delivery to enabled authorities. `POST /incidents/{incident_id}/notify` remains available for re-sending an existing incident. Enable `auto_notify` in `/streams/start` to send notifications for model detections as well.

Copy `.env.example` to `.env` and set SMTP and/or Twilio variables. A notification without provider credentials is recorded as failed; the service never claims a recipient was contacted when it was not.

## Send From Reporter Gmail

Set the Google OAuth values in `.env`, create a Google OAuth web client, and register `http://127.0.0.1:8001/auth/google/callback` as its redirect URI. Users then use the existing sign-in or sign-up page to grant the Gmail send permission. Reports created in that browser session are sent from the reporter's authorized Gmail; camera-only detections retain the configured service SMTP sender.

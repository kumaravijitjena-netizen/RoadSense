# RoadSense

## Road hazard detection and reporting system

---

## What problem does it solve?

Potholes and damaged manholes are a regular problem on many roads. They can cause accidents, damage vehicles, and make travel unsafe, especially at night or during rain. The bigger issue is that these problems are often reported late, without proper location details, and sometimes without any photo proof.

RoadSense was built to make this process faster. It can spot a pothole or manhole through a live camera feed, create an incident, save the location, and send an email notification. A person can also report an issue manually with their name, location, description, and photo.

This project is an MVP. The main aim is to prove that detection, reporting, mapping, and notification can work together in one system.

---

## What is RoadSense?

RoadSense is a web application with a React frontend and a Python backend. It has two ways to create an incident:

1. **Live detection** - the camera feed is checked by the pothole/manhole model.
2. **Manual report** - a user fills in the report form and can attach a photo.

After an incident is created, it is saved in the database, shown in the reported-incidents list, placed on the satellite map when coordinates are available, and emailed to configured contacts automatically.

---

## Main features

- Detects potholes and manholes from a live camera feed.
- Supports trained YOLO models.
- Shows the live processed video feed with detection boxes.
- Lets a user report an incident manually.
- Collects the reporter's name, email, named location, hazard type, and details.
- Allows optional GPS location and photo upload.
- Keeps a history of reported and detected incidents.
- Shows incidents on a real satellite map.
- Sends notification emails automatically after a report or valid detection.
- Uses live WebSocket updates so the dashboard can update without refreshing.
- Includes the backend work needed for Google sign-in and sending through a user's Gmail account.

---

## How live detection works

The live detection feature uses the camera attached to the device. The backend reads frames from the camera and sends them to the selected YOLO model.

The basic flow is:

1. The user starts the live camera.
2. OpenCV reads frames from the webcam, video file, or supported camera source.
3. The YOLO model checks every frame for potholes and manholes.
4. When it finds one, RoadSense draws a box around it in the live feed.
5. A new incident is created if it is not a duplicate.
6. The incident becomes visible in the dashboard and can trigger an email automatically.

The system uses a short duplicate window of 30 seconds for the same hazard type and source. This is important because a camera may see the same pothole in many consecutive frames. Without this check, one pothole could create many emails and many duplicate reports.

---

## Models used

The project currently supports two trained model versions:

- `pothole_manhole_v1`
- `pothole_manhole_v2_augmented`

The second model is used by default in the frontend. The model files are stored in the backend project under the `runs` folder. This makes it possible to test different training versions without rebuilding the full application.

The current classes are intentionally simple:

- Pothole
- Manhole

Keeping the first version focused makes testing easier. Other hazard types can be added later once the detection quality is reliable enough.

---

## Manual incident reporting

Not every problem will be caught by a live camera. For that reason, RoadSense also has a manual reporting form.

The person reporting an issue can enter:

| Information | Why it is collected |
|---|---|
| Hazard type | Identifies whether it is a pothole, manhole, or another issue |
| Reporter name | Shows who submitted the report |
| Reporter email | Lets the system keep contact details if needed |
| Named location | Gives a readable road, area, or address |
| GPS coordinates | Places the incident accurately on the map |
| Description | Adds useful context about the issue |
| Photo | Gives visual proof of the road condition |

The name, location, and hazard type are required. GPS coordinates, description, email, and photo are optional, because a report should still be possible when the person does not have every detail available.

Supported photo types are JPEG, PNG, and WebP. The backend stores the uploaded photo locally for the MVP.

---

## Incident list and history

The incident section is deliberately kept simple. It shows the reports that have been made, with:

- Hazard type
- Incident ID
- Location
- Time reported or detected

The earlier design included extra control panels and confidence percentages in this area. Those were removed so the page works as a clear incident history instead of looking like an operator-only screen.

The incident database keeps more information in the background, including source, model, status, photo path, coordinates, and timestamps. This means the application can grow later without needing to redesign the data structure.

---

## Live satellite map

RoadSense uses Leaflet with Esri World Imagery satellite tiles. This is a real satellite map, not a drawn placeholder.

When the user allows browser location access, the map can center on their current device location. It also shows markers for incidents that have GPS coordinates.

The map helps answer a simple question quickly: **where are the reported road hazards?**

For this MVP, the map is mainly for viewing incident positions. A future version can add route planning, area filters, heatmaps, and authority zones.

---

## Automatic email notification

Once an incident is created, RoadSense can notify the registered authority contacts automatically. The reporter does not need to press a separate notification button.

The email includes useful information such as:

- Incident ID
- Hazard type
- Source of the report
- Named location
- GPS coordinates, if available
- Reporter details, if available
- Date and time

Emails are sent in the background. This means the user gets a quick response from the website while the backend handles the notification.

The current MVP has been tested with SMTP email delivery. The backend records notification status in its database, so it is possible to see whether the mail provider accepted the message for delivery.

Email credentials are stored in a local `.env` file and are not included in the project repository.

---

## Sending from the user's own Gmail account

The long-term idea is that a user should be able to sign in with Google and allow RoadSense to send the report from their own Gmail account, instead of always sending from a single project mailbox.

The application already contains the main backend pieces for this:

- Google OAuth start route
- Google OAuth callback route
- Sign-in and sign-up pages that begin Google authorization
- Local user session storage
- Token refresh support
- Gmail API sending code

To activate this feature, a Google Cloud OAuth Web Client must be created. Its redirect address should be:

```text
http://127.0.0.1:8001/auth/google/callback
```

The client ID and secret then need to be placed in the backend `.env` file. The Google permission requested is `gmail.send`, which only permits email sending after the user has personally allowed it.

For the MVP, SMTP is the tested notification route. Google OAuth is the next activation step, not a fake sign-in screen.

---

## Backend design

The backend is built with FastAPI. It handles the part of the project that needs to run outside the browser: AI model loading, camera processing, databases, images, emails, and live updates.

| Part | Role in the project |
|---|---|
| FastAPI | Provides APIs, uploads, and WebSocket routes |
| Uvicorn | Runs the FastAPI service locally |
| Ultralytics YOLO | Detects potholes and manholes |
| OpenCV | Reads and processes camera frames |
| SQLite | Stores reports, authority contacts, notifications, and sessions |
| SMTP | Sends automatic MVP email notifications |
| Gmail API | Supports user-owned Gmail sending after OAuth is configured |

The backend runs locally on port `8001` during development.

---

## Frontend design

The frontend is made with React, TypeScript, Vite, Tailwind CSS, and Lucide icons. It runs locally on port `3000` during development.

The interface was changed based on the MVP goal:

- The unnecessary left-side navigation was removed.
- The layout was corrected so headings no longer sit behind the camera panel.
- The live camera area now focuses on the actual camera feed.
- The report form is built around useful reporting details.
- The incident queue was simplified into an incidents-reported view.
- The map uses live device location and real satellite imagery.

The frontend communicates with the backend through normal HTTP APIs for reporting and setup, and a WebSocket connection for live updates.

---

## Important API routes

| Route | What it does |
|---|---|
| `GET /health` | Checks backend and model status |
| `POST /predict` | Runs detection on one uploaded image |
| `POST /streams/start` | Starts live camera detection |
| `POST /streams/stop` | Stops the live feed |
| `GET /streams/mjpeg` | Returns the annotated live video stream |
| `POST /incidents/report` | Saves a manual incident report and optional photo |
| `GET /incidents` | Returns incident history |
| `POST /locations` | Saves a device location |
| `GET /locations/latest` | Gets recently saved locations |
| `GET /authorities` | Lists people or contacts who receive reports |
| `POST /authorities` | Adds an authority contact |
| `GET /auth/google/start` | Starts Google sign-in |
| `GET /auth/google/callback` | Completes Google sign-in |
| `GET /auth/me` | Returns the current signed-in user |
| `WS /ws/live` | Sends live incident, location, and stream updates |

---

## Testing done so far

The following parts were checked during development:

- Both YOLO model versions loaded through the backend.
- The backend health check returned a healthy response.
- The Python backend compiled successfully.
- The TypeScript frontend type check completed successfully.
- A manual report with a photo upload was accepted.
- Reports were saved in SQLite and appeared in the incident list.
- Named locations were saved and displayed.
- The Esri satellite map loaded correctly.
- Automatic SMTP email notification was sent to the configured test recipient and logged as sent by the SMTP provider.
- A structured report containing a name and named location was tested successfully.

---

## Current limitations

This is a working MVP, so a few things are still intentionally local or basic:

- The application currently uses SQLite. A multi-user production version should use PostgreSQL or another server database.
- Browser camera and location access depend on user permission.
- The model needs more testing across rain, poor lighting, different camera angles, and different road surfaces.
- OAuth code is ready, but Google Cloud client credentials must still be created to activate real Google sign-in.
- The backend can confirm that the SMTP provider accepted a mail, but inbox delivery can still be affected by spam filters or mailbox rules.
- Production deployment would need HTTPS, secure cookies, encrypted token storage, secret management, rate limiting, and stronger audit logs.

---

## What can be added next?

1. Activate Google OAuth so each person can send from their own Gmail account.
2. Add a small status indicator showing whether Gmail is connected.
3. Show photo previews inside the incident history.
4. Send different reports to different authorities based on location.
5. Add SMS or push alerts for urgent hazards.
6. Merge nearby duplicate reports using time and distance.
7. Add repair status updates from an authority dashboard.
8. Add heatmaps to identify areas with repeated road damage.
9. Build a mobile-first version for quick roadside reporting.

---

## Suggested demo flow

1. Start by explaining the road-safety problem.
2. Open the RoadSense dashboard.
3. Show the live camera section and start the feed.
4. Explain that the YOLO model checks frames for potholes and manholes.
5. Show the report form and enter a sample name, location, and hazard type.
6. Attach a sample image if available.
7. Submit the report.
8. Show the report in the incidents-reported list.
9. Show its position on the satellite map.
10. Explain that the backend sends a notification automatically.
11. End by explaining that the next step is activating Google OAuth for send-from-user Gmail reporting.

---

## Conclusion

RoadSense shows how a road issue can move from detection to reporting in one place. Instead of relying only on people noticing a pothole and manually finding the right contact, the system can capture evidence, save the location, keep a history, and notify someone automatically.

The MVP focuses on potholes and manholes because they are common, visible, and important safety issues. From here, the same system can be expanded into a larger reporting and road-maintenance platform.

# RoadSense Project Status

Last updated: 18 September 2026

## What RoadSense Is

RoadSense is a road-hazard reporting and response platform. It lets people report potholes, open manholes, cracks, bumps, and other hazards using a form, uploaded media, SMS, or live camera detection. Authorities have a separate workspace to track reports, publish work updates, and upload completion proof.

The application has a React frontend and a FastAPI/Python backend. It currently runs locally at:

- Frontend: `http://127.0.0.1:3000`
- Backend API: `http://127.0.0.1:8001`

## Implemented Features

## Implementation Status At A Glance

| Area | Status | Reality today |
| --- | --- | --- |
| Public reporting form | Implemented | Saves reports, addresses, details, evidence metadata, and available GPS to Supabase PostgreSQL. |
| Photo/video upload | Implemented | Mirrors supported files to private Supabase Storage and preserves local development copies. |
| Photo GPS extraction | Implemented | Uses real EXIF GPS when the uploaded original file preserves it. |
| Live browser camera | Implemented | Opens device camera, sends frames to backend, and draws detection boxes. |
| AI detection | Implemented with installed models | Detects only the classes present in the available model weights. |
| Incident map | Implemented | Real Leaflet satellite map, real coordinates only, marker detail and fullscreen. |
| Zones | Implemented | Density zones are calculated from reports with confirmed coordinates. |
| Authority dashboard | Implemented | Authorities can post work-started updates and submit resolution proof. |
| Email notifications | Implemented, configuration dependent | Sends only when SMTP or connected Gmail is correctly configured. |
| Email image attachment and map link | Implemented | Attachment/location details are generated when evidence and coordinates exist. |
| SMS reporting | Implemented, configuration dependent | Requires Twilio public webhook and translation service configuration. |
| WhatsApp alerts | Code implemented, not configured | Requires Twilio WhatsApp Business sender, opt-in recipients, and approved messaging rules. |
| English/Hindi UI | Implemented for core screens | Main UI and authority flow are bilingual; some newer detail strings remain English. |
| Password sign-up/sign-in | Implemented | Stored in Supabase PostgreSQL. |
| Password reset | Implemented | Uses generated code flow; actual delivery depends on configured email. |
| Google OAuth | Implemented, setup pending | Backend/UI flow exists; Google Console and production redirect configuration must be completed. |
| Supabase PostgreSQL cloud database | Implemented | SQLite records and schema have been migrated through the Session pooler. |
| Supabase Storage | Implemented | Evidence uploads mirror to the private `incident-media` bucket; the backend serves private files. |
| Manual map pin | Implemented | Satellite pin picker stores the selected incident coordinates as `manual_pin`. |
| Production security hardening | Not implemented | MVP needs roles, rate limiting, audit policy, backups, and secret rotation. |

## UI Walkthrough

### 1. Main Dashboard

**Implemented**

- A branded RoadSense landing/dashboard with the "The road is speaking" message.
- A responsive navigation dock for Overview, Live, Incidents, and Routes.
- User access through the account avatar rather than a cluttered operational header.
- English/Hindi language switcher on supported screens.
- Responsive layout for desktop and mobile widths.
- Background grid and visual system for the map/dashboard pages.
- Header and footer clutter previously identified during design review was removed or reduced.

**How it behaves**

- The dashboard retrieves incidents from the backend and listens to WebSocket updates.
- New reports or authority status changes update the incident list.
- Selecting a report scrolls/focuses related details and map content.

**Not yet complete**

- No admin-level dashboard analytics such as totals over time, response SLA, or geographical heatmap analytics.
- Some small labels introduced after the translation work are currently English-only.
- The dashboard has no offline mode or progressive-web-app install support.

### 2. Report Incident Form

**Implemented**

- Hazard type selector: pothole, manhole, crack, bump, and other.
- Required reporter name and named location.
- Optional reporter email, address line, area, city, postal code, landmark, and detailed description.
- **Add GPS** button, which requests browser/device geolocation.
- Upload field for photos and video evidence.
- **Pick on map** opens a satellite map where the reporter can place an exact manual incident pin.
- On-screen evidence preview.
- File support for JPEG, PNG, WebP, HEIC, HEIF, MP4, WebM, and MOV.
- Uploaded-photo metadata check with clear status text:
  - Photo GPS found: report uses photo coordinates.
  - No photo GPS found: report uses device GPS only if the user attached it.
- Success/failure toast messages after report submission.

**How location selection works now**

1. If an original image contains GPS metadata, that location is used.
2. If the image has no GPS but Add GPS was used, current browser/device coordinates are used.
3. If the reporter uses Pick on map, that manually selected pin is used.
4. If none of the above exists, the report is saved with address text but no coordinate marker.

**Not yet complete**

- No forward/reverse geocoding to automatically turn coordinates into a postal address.
- No OCR for address signs in an image.
- No automatic location inference from road pixels; that would be unreliable and should not be claimed as a real location.
- Videos are accepted as evidence, but video metadata GPS extraction has not been implemented.

### 3. Live Camera and Detection UI

**Implemented**

- Start/stop device-camera control.
- Camera source selection that prefers an ordinary webcam over known phone/continuity camera labels where possible.
- Browser permission failure messages for denied/missing cameras.
- Real-time preview using the browser media stream.
- Periodic upload of browser frames to the FastAPI backend.
- Detection count and model response handling.
- Canvas overlay with bounding boxes and confidence labels.
- Automatic incident creation from detected hazards with a short duplicate-prevention window.
- Automatic authority notification hook for live detections.

**Not yet complete**

- Detection quality depends entirely on the supplied trained model; UI cannot make a model recognize unseen or poorly-trained classes.
- There is no continuous server-side video recording or event replay timeline.
- There is no detection confidence settings UI for ordinary users.
- No per-model selector is exposed in the final public workflow.
- Live location is current device location during camera use, not geolocation inferred from the camera image.

### 4. Incident Queue and Report History

**Implemented**

- Incident list with type, address/location summary, date/time, and status.
- Search/filter behavior in the queue.
- Incident selection and detailed report panel.
- Status values: open, acknowledged/work in progress, resolved, and false positive in the backend model.
- Clear history control for locally stored incident history.
- Report media is visible in related details where supported.

**Not yet complete**

- No advanced filtering by date, zone, ward, authority, hazard type, or status across a large data set.
- Clear-history is an MVP action and needs a protected admin role and stronger confirmation policy before public deployment.
- No export to CSV/PDF yet.
- No full immutable audit timeline shown to regular users.

### 5. Interactive Satellite Map

**Implemented**

- Real Leaflet map using Esri World Imagery tiles.
- Standard zoom controls.
- Browser/device position marker when location permission is allowed.
- Incident markers only for reports with confirmed GPS coordinates.
- Marker popup with hazard type, report location, and report photo/video where available.
- Clicking markers updates the selected incident detail card.
- Detail card contains report status, address, description, authority update, and completion proof.
- Fullscreen map control.
- A map popup and selected state automatically center/fly to a selected report.
- Colored density zone overlays.

**Important correction made**

- Reports without GPS are no longer placed near Bengaluru as a visual fallback. That fallback was misleading and has been removed.

**Not yet complete**

- No hand-drawn zones or administrator-defined ward boundaries.
- Current zones use geographic cells rather than municipal GIS ward polygons.
- No route optimization/navigation for authority teams.
- No clustering for very large report volumes.
- No offline tiles.

### 6. Zone System

**Implemented**

- Automatic grouping of nearby confirmed-coordinate reports.
- Green, blue, yellow, orange, and red severity system.
- Public map zone circles.
- Authority dashboard zone summary pills.
- Automatic email escalation at report totals 3, 5, and 8 for a zone.
- Database record to stop duplicate alert emails at the same threshold.

**Not yet complete**

- Zones cannot yet be edited or named by authorities.
- Thresholds are hard-coded, not configurable from the UI.
- Zone email recipients are enabled authorities; specialized department routing by hazard type/ward is not yet built.
- Zone decay rules are not implemented; resolved reports still influence the current density calculation unless excluded by status logic.

### 7. Authority Dashboard

**Implemented**

- Completely separate authority sign-in route and dashboard.
- Temporary local authority account for MVP access.
- List of open and resolved reports.
- Selected incident address, coordinates, Google Maps link, and original evidence.
- Text field for a public work-started update.
- **Mark work started** changes status to acknowledged.
- Completion photo/video upload.
- **Submit proof and resolve** adds proof, creates a final authority update, and marks the incident resolved.
- Public dashboard/map detail reflects the update and proof through the backend event flow.
- English/Hindi primary authority workflows.

**Not yet complete**

- No separate authority accounts per individual or department yet; there is one shared temporary portal credential for development.
- No assignment of a report to a named field worker.
- No work schedules, comments between officers, cost estimates, or work-order numbers.
- No proof review/approval workflow by a supervisor.
- No authority-specific GIS territory filtering.
- No push notification or WhatsApp UI toggle for authorities yet.

### 8. Accounts, Sign-In, and Account Page

**Implemented**

- Standard sign-up with email/password.
- Standard sign-in with email/password.
- Password reset request, confirmation-code check, then new-password form.
- Google OAuth sign-in/connection route.
- Account card with account information and a controlled flip interaction.
- Account information page and profile update actions.
- Logout confirmation interaction.

**Not yet complete**

- No email verification during account creation.
- No account deletion flow.
- No multi-factor authentication.
- Google OAuth production verification and consent-screen release are not complete.
- No organization management or team invitations.

### 9. Email, SMS, and WhatsApp UI/Delivery

**Implemented**

- Automatic new-report notification flow.
- Email content includes report context, address, coordinate source, map link, evidence note, and India Standard Time.
- Evidence image attachment can include a location footer.
- SMTP result is logged in the notifications table.
- Google-connected users can send via their own Gmail when the OAuth connection is valid.
- SMS reporting feature has an endpoint and configuration guide.
- WhatsApp backend sending function is present and can be enabled per authority.

**Not yet complete**

- No delivery-status dashboard showing every outbound email/SMS/WhatsApp result in the UI.
- No resend button for failed notifications.
- No WhatsApp sender credentials are configured yet.
- No user-facing WhatsApp opt-in UI.
- No scheduled reminder/escalation workflow for unresolved reports.
- No multilingual outbound WhatsApp template system.


### Public Reporting

- Report potholes, manholes, cracks, bumps, and other hazards.
- Collect reporter name, email, location name, address, area, city, postal code, landmark, and report details.
- Upload report evidence: JPEG, PNG, WebP, HEIC, HEIF, MP4, WebM, and MOV.
- Preview uploaded images and video before submitting.
- Attach current browser/device GPS when the user chooses **Add GPS**.
- Inspect an uploaded original image for embedded photo GPS before reporting.
- Use photo metadata coordinates in preference to browser/device coordinates when present.
- Clearly indicate whether a report uses photo GPS, reporter-device GPS, live-camera GPS, or has no confirmed GPS.
- Extract a Google Maps link for reports with coordinates or a location search link when an address was supplied.

### Photo Location Behaviour

- RoadSense reads EXIF GPS from original images, including HEIC/HEIF when the metadata has been preserved.
- Screenshots, edited files, downloaded social-media images, and some file-transfer methods can strip GPS metadata. In that case, RoadSense does not invent a location.
- Reports without real coordinates are retained in the queue but are no longer plotted using the old Bengaluru fallback marker.

### Live Camera Detection

- Browser camera can be opened through the website.
- Frames are periodically sent to the backend for model inference.
- Detected hazards display bounding boxes over the live camera preview.
- A live detection creates a deduplicated incident and can automatically notify authorities.
- Browser camera and live stream error states are shown to the user.

### Incident Map and History

- Satellite map uses Leaflet and Esri World Imagery.
- Shows user/device location when location permission is granted.
- Shows reported incidents with actual stored coordinates.
- Clicking a marker selects the incident and opens its map popup.
- The dashboard presents a detailed selected-report card with address, description, authority status, updates, and completion evidence.
- Supports image and video evidence in map-related report views.
- Map can be opened in browser fullscreen.
- Report history has a clear-history action for local incident records.

### Zones and Escalation

- Nearby GPS reports are grouped into fixed geographic density zones.
- Zone colors are based on report count:
  - Green: 1 report
  - Blue: 2 reports
  - Yellow: 3-4 reports
  - Orange: 5-7 reports
  - Red: 8 or more reports
- Zones appear as colored overlays on the main satellite map.
- The authority dashboard has a live zone summary.
- Yellow, orange, and red thresholds trigger one escalation email per zone threshold to enabled authorities.
- `zone_alerts` prevents duplicate escalation emails for the same threshold.

### Authority Workspace

- Separate authority sign-in route: `/authority/sign-in`.
- Authority dashboard lists all reports and lets an authority select a report.
- Selected report shows report address, coordinate map link, original evidence, and status.
- Authority can add a public work-started update; this changes the incident to `acknowledged`.
- Authority can upload photo/video completion proof and mark the report `resolved`.
- Public dashboard receives status and authority updates through the live event flow and selected report detail.
- A temporary local authority credential is configured for development only. It must be replaced before production use.

### Accounts and Authentication

- Normal sign-up with name, email, and password.
- Normal sign-in with email and password.
- Password reset flow with generated confirmation code before allowing a new password.
- Google OAuth flow exists for user account connection and Gmail send permission.
- Account page, profile settings, account information page, sign-out confirmation, and user-facing account UI are implemented.
- Separate authority credential flow is intentionally not shown in the normal user dashboard.

### Notifications

- Email notifications are sent for new reports and live detections through SMTP.
- Google-connected reporters can send authority notification mail through their own Gmail account when the OAuth connection is available.
- Email includes hazard details, address, coordinate source, map link, reporter information, and evidence attachment when available.
- Still-image attachments receive a location footer when location data exists.
- Email timestamps now display in India Standard Time, for example: `17 Sep 2026, 09:43:23 PM IST`.
- SMS notification support exists through Twilio configuration.
- Inbound Twilio SMS reporting can create an incident after translation to English through a configured translation service.
- WhatsApp notification support has been added to the backend. It is opt-in per authority and uses Twilio WhatsApp once configured.

### Language Support

- Main user experience supports English and Hindi through the language switcher.
- Authority pages include English/Hindi text for their key workflows.
- SMS processing is designed to translate supported incoming languages to English before creating and emailing the report.

## Current Data Storage

RoadSense currently uses a local SQLite file:

`road_sense_web/roadsense_backend/data/roadsense.db`

Stored data currently includes:

- User accounts and sessions.
- Authorities and notification preferences.
- Incidents and all location/address fields.
- Live device locations.
- Notification delivery logs.
- Google OAuth records.
- SMS reports and translated message content.
- Resolution proof records.
- Authority work updates.
- Password reset records.
- Zone alert delivery records.

Uploaded media is currently saved locally under:

`road_sense_web/roadsense_backend/data/media`

## Current Database Tables

The current SQLite schema uses these main tables:

1. `users`
2. `user_sessions`
3. `authorities`
4. `incidents`
5. `locations`
6. `notifications`
7. `google_accounts`
8. `oauth_states`
9. `sms_reports`
10. `resolution_proofs`
11. `authority_updates`
12. `password_resets`
13. `zone_alerts`

## Services That Need Configuration

These features are built but depend on valid secrets and verified third-party service setup.

### SMTP Email

Required environment settings:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_TLS`
- `SMTP_FROM`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

The current code records delivery failures in the `notifications` table. Email can fail because of incorrect credentials, an expired Gmail app password, recipient filtering, or provider policy.

### Google OAuth / Gmail Sending

Required settings:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI`

Google Cloud must also have the exact redirect URI, consent-screen scopes, and test users configured. OAuth must be completed by the user in the browser for mail to be sent from that user's Gmail account.

### Twilio SMS

Required settings:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM`

Inbound SMS additionally needs a public HTTPS webhook URL pointing to:

`/webhooks/twilio/sms`

### Twilio WhatsApp

Required settings:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_FROM`

The sender must be a registered WhatsApp Business/Twilio sender. Recipient phone numbers must be opted in, and template approval may be required outside the allowed customer-service window. WhatsApp is disabled for every authority unless `whatsapp_enabled` is explicitly true.

### SMS Translation

Required settings:

- `TRANSLATION_URL`
- Optional `TRANSLATION_API_KEY`

This should point to a LibreTranslate-compatible service or equivalent translation provider.

## Important Current Limitations

- Local media copies are a development cache. Supabase Storage is the durable media source after deployment.
- The temporary authority credentials are only for local testing and must not be used in production.
- GPS can only come from browser permission, original image metadata, live-camera location, or a future manual map-pin feature. RoadSense cannot infer a location from the pixels of a road photo.
- The live detection model only recognizes classes included in the installed model weights. Crack/bump models must be placed in the configured model directory or supplied by `ROADSENSE_MODELS`.
- Sending SMS and WhatsApp at scale is not free; a verified provider account and consent-compliant recipients are required.
- User/authority authorization is functional for the MVP but needs production security review, rate limiting, secret rotation, database access controls, and audits.

## Recommended Next Steps

1. Replace temporary authority credentials with managed authority accounts and roles.
2. Complete Google OAuth production verification and configure the deployed callback URL.
3. Configure Twilio SMS and WhatsApp Business sender details.
4. Add rate limiting, audit logs, data retention, and access rules before public release.
5. Deploy the backend with the Supabase environment variables.

## Verification Performed Recently

- Python backend syntax check: passed.
- Frontend TypeScript check: passed.
- Supabase PostgreSQL migration: completed (5 users, 4 incidents, 182 locations, 1 authority update).
- Supabase-backed API checks: `/health`, `/incidents`, `/locations/latest`, `/zones`, and `/authorities` returned `200`.
- Supabase Storage: 15 historical media files mirrored; private upload, retrieval, and deletion checks passed.
- Local health endpoint: returned HTTP 200 after backend restarts.
- Photo metadata inspection: verified that the examined uploaded OnePlus file had camera/date EXIF but no GPS metadata block.
- Email timestamp rendering: verified as India Standard Time.

## Key Project Locations

- Backend: `road_sense_web/roadsense_backend/main.py`
- Frontend pages: `road_sense_web/roadsense_frontend/client/src/pages`
- Map component: `road_sense_web/roadsense_frontend/client/src/components/SatelliteMap.tsx`
- API client: `road_sense_web/roadsense_frontend/client/src/lib/roadsense-api.ts`
- Environment template: `road_sense_web/roadsense_backend/.env.example`
- SMS guide: `road_sense_web/roadsense_backend/SMS_REPORTING.md`

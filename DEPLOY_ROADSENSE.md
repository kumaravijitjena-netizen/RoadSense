# Deploy RoadSense

This project is ready to deploy as one Docker web service. The FastAPI backend serves the built React frontend, so the public website and API use the same URL.

## Deploy Through VS Code

Open the RoadSense project folder in VS Code:

```text
C:\Users\kumar\OneDrive\Documents\ChatGPT\RoadSense
```

Open the integrated terminal with **Terminal > New Terminal**. Create an empty GitHub repository named `roadsense` first, then run these commands in the VS Code terminal. Replace `YOUR-GITHUB-USERNAME` with your GitHub username.

```powershell
git init
git add .
git commit -m "Deploy RoadSense"
git branch -M main
git remote add origin https://github.com/YOUR-GITHUB-USERNAME/roadsense.git
git push -u origin main
```

If VS Code asks you to sign in to GitHub, complete that sign-in in VS Code. Do not upload the local `.env` file, database, or private report evidence.

After the GitHub push, use Render's Blueprint deployment screen to select the repository. Render builds the existing `Dockerfile` automatically. VS Code is used for editing, testing, committing, and pushing the project; Render provides the public website URL.

## Before Deploying

1. Create a GitHub repository, for example `roadsense`.
2. Upload the complete project folder to that repository.
3. Do not upload `road_sense_web/roadsense_backend/.env` or any private credentials.
4. Create a Render account at https://render.com and connect GitHub.

## Deploy on Render

1. In Render, choose **New +** and then **Blueprint**.
2. Select the GitHub repository containing RoadSense.
3. Render detects `render.yaml` in the project root.
4. Create the `roadsense` web service.
5. Use at least the **Starter** plan. YOLO model loading is too heavy for a basic static site host.
6. Wait for the Docker build and deployment to finish.
7. Open the generated URL, normally similar to:

```text
https://roadsense.onrender.com
```

## Render Environment Variables

In the Render service settings, add the real values for these variables. They are intentionally blank in `render.yaml`.

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_FROM=your-sender@gmail.com
SMTP_USERNAME=your-sender@gmail.com
SMTP_PASSWORD=your-gmail-app-password
```

These are required for automatic authority emails.

```env
GOOGLE_OAUTH_CLIENT_ID=your-google-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-google-client-secret
GOOGLE_OAUTH_REDIRECT_URI=https://YOUR-RENDER-URL/auth/google/callback
```

These are required only when users should sign in and send reports from their own Gmail accounts.

Optional SMS values:

```env
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM=
```

## Google OAuth Setup

1. Open Google Cloud Console.
2. Create or select a project.
3. Enable the Gmail API.
4. Create an OAuth 2.0 Web Client.
5. Add this exact authorized redirect URI:

```text
https://YOUR-RENDER-URL/auth/google/callback
```

6. Copy the client ID and client secret into Render environment variables.
7. Add your deployed URL to the OAuth consent screen's authorized domains if Google asks for it.

## After Deployment

1. Visit the Render URL on a phone or desktop.
2. Allow camera permission when starting live detection.
3. Allow location permission when attaching GPS.
4. Submit a test report.
5. Confirm the report appears in **Reported incidents**.
6. Confirm the configured authority/test email receives the notification.
7. Test Google sign-in after OAuth is configured.

## Important Notes

- A deployed service cannot access a visitor's laptop camera from the server. RoadSense correctly uses each visitor's browser camera and sends sampled frames to the deployed backend for YOLO detection.
- Render's local disk is not permanent. For a production version, move the SQLite database and uploaded report evidence to managed storage such as PostgreSQL plus object storage.
- Never commit `.env`, Gmail app passwords, OAuth client secrets, or a real local incident database to GitHub.
- The project includes a `Dockerfile` and `render.yaml` specifically for this deployment path.

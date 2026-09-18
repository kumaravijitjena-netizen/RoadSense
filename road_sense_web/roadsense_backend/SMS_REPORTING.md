# SMS Reporting Setup

RoadSense accepts reports from any phone through Twilio. A sender texts the reporting number in this format:

```
POTHOLE | MG Road, Bengaluru | Large pothole near the metro entrance
```

`MANHOLE` can replace `POTHOLE`. Any other first word is recorded as an `other` road hazard. The first text segment after `|` is the location; the final segment is optional details.

## Configure Twilio

1. Create a Twilio account and obtain an SMS-capable phone number. A trial account accepts messages only from verified numbers.
2. In Twilio Console, open **Phone Numbers**, select the reporting number, then under **Messaging** set **A message comes in** to `POST` and enter:
   ```
   https://YOUR-PUBLIC-ROADSENSE-URL/webhooks/twilio/sms
   ```
3. Set these environment variables on the RoadSense host:
   ```
   TWILIO_ACCOUNT_SID=...
   TWILIO_AUTH_TOKEN=...
   TWILIO_FROM=+1234567890
   TWILIO_REPORTING_NUMBER=+1234567890
   TWILIO_SMS_WEBHOOK_URL=https://YOUR-PUBLIC-ROADSENSE-URL/webhooks/twilio/sms
   ```
4. Configure at least one authority email in RoadSense. Each valid SMS creates an incident and emails enabled authorities automatically.

## Translation to English

Configure a LibreTranslate-compatible service before enabling the Twilio webhook:

```bash
TRANSLATION_URL=https://YOUR-TRANSLATION-SERVICE/translate
TRANSLATION_API_KEY=optional-provider-key
```

RoadSense sends the received text with automatic source-language detection and English as the target language. The English version determines the hazard and report details used in the authority email; the original SMS and the English translation are retained in the local SMS audit record. If translation is unavailable, RoadSense returns an error to Twilio and does not send an ambiguous authority email.

## Adding Detection Models

Drop each compatible Ultralytics weight file into this layout and restart the backend:

```text
runs/
  cracks/weights/best.pt
  bumps/weights/best.pt
```

RoadSense registers `cracks` and `bumps` automatically. Detection class names emitted by the model become the incident hazard type. Models stored elsewhere can be configured with `ROADSENSE_MODELS` in the environment.

The webhook verifies Twilio's signed request. `TWILIO_SMS_WEBHOOK_URL` must exactly match the public URL configured in Twilio, including `https` and any path. The sender's number is stored as the reporter identity, and duplicate webhook retries do not create duplicate reports.

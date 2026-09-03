# FRAB Voice Escalation Agent

An **isolated** microservice that lets an analyst escalate a completed FRAB case
by **phone call**. When the analyst clicks **ESCALATE BY VOICE** in the Case Book,
this service fetches the completed investigation from the FRAB backend, feeds that
context into a Vapi voice assistant, and places an outbound call via Twilio.

> This service does **not** touch the synthetic bank, Firestore bank data, the
> transaction simulator, the rule engine, or any investigation agent. It only
> **reads** completed case data through the FRAB HTTP API.

---

## Architecture

```
Analyst clicks "ESCALATE BY VOICE"
        │  { case_id, recipient_phone }
        ▼
POST /api/voice/escalate
        │
        ├─► GET /cases/{case_id}          ┐
        ├─► GET /alerts/{alert_id}        ├─ FRAB backend (read-only)
        └─► GET /investigation/{alert_id} ┘
        │
        ▼
  Build dynamic call context (Case 91 talks about Case 91)
        │
        ▼
  Vapi outbound call  ──►  Twilio number  ──►  Analyst's phone
        │
        ▼
  Vapi webhook events  ──►  POST /api/voice/webhook
        │
        ▼
  Call status: REQUESTED → CALLING → CONNECTED → COMPLETED
        │
        ▼
  Audit event stored  ──►  GET /api/voice/audit/{case_id}  (Case Book Page 08)
```

---

## Prerequisites (accounts your teammate creates)

1. **Vapi account** — https://vapi.ai
2. **Twilio account** — https://twilio.com
3. **Twilio phone number** capable of the required calls
   - Vapi's free numbers are US-only and can't call India. For an India demo,
     import a suitable **Twilio** number instead.

Collect:
- `VAPI_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- Twilio phone number

---

## One-time Vapi setup

### 1. Import Twilio number into Vapi
Dashboard → **Phone Numbers** → **Create Phone Number** → **Import Twilio**

Enter your Twilio phone number, Account SID, and Auth Token.
After importing, copy the **`VAPI_PHONE_NUMBER_ID`**.

### 2. Create the assistant
Dashboard → **Assistants** → **Create Assistant**

Name: `FRAB Voice Escalation Agent`

System prompt:

```
You are the FRAB Voice Escalation Agent.
You represent a financial-crime investigation system and communicate
investigation findings to an authorized financial-crime analyst or
compliance officer.
Your job is to verbally summarize an investigation that has already been
completed by FRAB.

You MUST:
- identify the case ID
- state the alert type
- state the risk level
- summarize the key verified evidence
- explain why FRAB generated its recommendation
- clearly distinguish verified evidence from FRAB's recommendation
- ask whether the recipient wants any additional information
- remain concise and professional

Never invent:
- transaction amounts
- customer information
- risk scores
- dates
- beneficiaries
- network relationships
- regulatory provisions
- investigation findings

Only use information supplied in the case context.
Do not claim that a person or transaction is legally guilty.
The investigation recommendation is decision support only. The authorized
human analyst remains responsible for the final decision.
If information is unavailable, say that it is unavailable rather than guessing.
```

Copy the **`VAPI_ASSISTANT_ID`**.

### 3. Test the call from Vapi dashboard FIRST
Before wiring the backend, place a test outbound call to your own phone from the
Vapi dashboard. Confirm the agent answers, speaks, understands questions, and
ends the call. Only then run this service.

---

## Local setup

```bash
cd voice_agent
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt

# Configure
cp .env.example .env    # then fill in your Vapi + Twilio values
```

Load the env vars and run (from the project root, so `voice_agent` is importable):

```bash
# from the repository root (one level above voice_agent/)
uvicorn voice_agent.main:app --reload --port 8001
```

Docs: `http://localhost:8001/docs`
Health: `curl http://localhost:8001/health`  →  `{"status":"ok","service":"voice-escalation-agent"}`

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `VAPI_API_KEY` | Yes | Vapi private key (server-side only) |
| `VAPI_ASSISTANT_ID` | Yes | The FRAB Voice Escalation assistant |
| `VAPI_PHONE_NUMBER_ID` | Yes | Imported Twilio number ID from Vapi |
| `TWILIO_ACCOUNT_SID` | For import | Only needed when importing the number |
| `TWILIO_AUTH_TOKEN` | For import | Only needed when importing the number |
| `TWILIO_PHONE_NUMBER` | For import | Your Twilio number, e.g. `+12015551234` |
| `FRAB_BACKEND_URL` | Yes | Synthetic bank / FRAB API base URL |
| `VAPI_WEBHOOK_URL` | Recommended | Public URL for Vapi status callbacks |
| `PORT` | No | Server port (Cloud Run sets this) |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated frontend origins |

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/voice/escalate` | Start a voice escalation call |
| GET | `/api/voice/calls/{call_id}` | Current call status + duration |
| GET | `/api/voice/audit` | All audit events (`?case_id=` to filter) |
| GET | `/api/voice/audit/{case_id}` | Audit events for one case |
| POST | `/api/voice/webhook` | Vapi call-status callback |
| GET | `/docs` | Swagger UI |

### POST /api/voice/escalate

Request:
```json
{
  "case_id": "CASE0001",
  "recipient_phone": "+919876543210"
}
```

Response:
```json
{
  "call_id": "VCALL-1A2B3C4D",
  "case_id": "CASE0001",
  "status": "CALLING",
  "recipient_masked": "+91......3210",
  "vapi_call_id": "vapi-uuid",
  "message": "Outbound call initiated for case CASE0001"
}
```

### GET /api/voice/calls/{call_id}

```json
{
  "call_id": "VCALL-1A2B3C4D",
  "case_id": "CASE0001",
  "status": "COMPLETED",
  "recipient_masked": "+91......3210",
  "vapi_call_id": "vapi-uuid",
  "started_at": "2026-09-03T19:42:10Z",
  "ended_at": "2026-09-03T19:44:24Z",
  "duration_seconds": 134,
  "duration_display": "02:14"
}
```

### Audit event (for Case Book Page 08)

```json
{
  "call_id": "VCALL-1A2B3C4D",
  "case_id": "CASE0001",
  "type": "VOICE_ESCALATION",
  "status": "COMPLETED",
  "timestamp": "2026-09-03T19:44:24Z",
  "recipient_masked": "+91......3210",
  "vapi_call_id": "vapi-uuid",
  "duration_seconds": 134,
  "summary": "Investigation summary delivered. Recipient acknowledged."
}
```

The full phone number is **never** stored in the audit record or returned to the
UI — only the masked form.

---

## Vapi webhook

Vapi POSTs call lifecycle events to `POST /api/voice/webhook`. Set
`VAPI_WEBHOOK_URL` to a **publicly reachable** URL:

- **Local dev** — expose the port with ngrok:
  ```bash
  ngrok http 8001
  # then set VAPI_WEBHOOK_URL=https://<ngrok-id>.ngrok.io/api/voice/webhook
  ```
- **Production** — `https://YOUR-VOICE-AGENT-CLOUD-RUN-URL/api/voice/webhook`

Handled events: `call-started` → CONNECTED, `call-ended` / `end-of-call-report`
→ COMPLETED (with duration + summary), `call-failed` → FAILED, `no-answer` → NO_ANSWER.

---

## Cloud Run deployment

The Docker build context is the `voice_agent/` folder itself:

```bash
cd voice_agent

gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/frab-repo/voice-escalation-agent

gcloud run deploy voice-escalation-agent \
  --image REGION-docker.pkg.dev/PROJECT_ID/frab-repo/voice-escalation-agent \
  --region REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars VAPI_API_KEY=...,VAPI_ASSISTANT_ID=...,VAPI_PHONE_NUMBER_ID=...,FRAB_BACKEND_URL=https://YOUR-BANK-URL,VAPI_WEBHOOK_URL=https://YOUR-VOICE-URL/api/voice/webhook
```

Cloud Run injects `PORT` automatically. Keep secrets out of Git — pass them via
`--set-env-vars` or Secret Manager, never in source.

---

## Quick end-to-end test (once Vapi is configured)

```bash
# 1. Health
curl http://localhost:8001/health

# 2. Escalate a real case
curl -X POST http://localhost:8001/api/voice/escalate \
  -H "Content-Type: application/json" \
  -d '{"case_id":"CASE0001","recipient_phone":"+91XXXXXXXXXX"}'

# 3. Poll status with the returned call_id
curl http://localhost:8001/api/voice/calls/VCALL-XXXXXXXX

# 4. After the call, read the audit trail
curl http://localhost:8001/api/voice/audit/CASE0001
```

---

## Scope boundary

**This service builds only:** Vapi + Twilio voice agent, the escalation endpoint,
call status tracking, the webhook, and the audit event.

**It does NOT modify:** the synthetic bank, Firestore bank data, the transaction
simulator, the rule engine, investigation agents (Watchman/Detective/Jurist/
Scribe/Supervisor), CVM/TEE, or the 3D investigation workspace.

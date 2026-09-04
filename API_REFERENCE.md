# FRAB Synthetic Bank — Frontend API Reference

Everything the frontend needs to connect to the two backend services.

- **Bank API** (this repo, `app/main.py`) — customers, transactions, alerts, cases, investigation
- **Voice Escalation API** (`voice_agent/main.py`) — outbound voice calls, call status, audit

Both are plain HTTP + JSON. CORS is enabled and configurable via the
`CORS_ALLOWED_ORIGINS` env var (already allows localhost:3000, 5173, 8080).

---

## Base URLs

| Environment | Bank API | Voice API |
|-------------|----------|-----------|
| Local | `http://localhost:8000` | `http://localhost:8021` |
| Cloud Run | `https://<your-bank-cloud-run-url>` | `https://<your-voice-cloud-run-url>` |

Set these as `VITE_API_BASE_URL` / `VITE_VOICE_API_URL` in the frontend `.env`.

---

# BANK API

## Health

```
GET /health
```
```json
{ "status": "ok", "service": "synthetic-bank" }
```

---

## Customers

### Get a customer
```
GET /customers/{customer_id}
```
Example: `GET /customers/C009001507`
```json
{
  "customer_id": "C009001507",
  "account_id": "ACC-C009001507",
  "customer_name": "…",
  "status": "ACTIVE",
  "city": "…"
}
```
404 if not found.

### Get a customer's KYC profile
```
GET /customers/{customer_id}/kyc
```
```json
{
  "customer_id": "C009001507",
  "kyc_status": "VERIFIED",
  "risk_category": "MEDIUM",
  "occupation": "STUDENT",
  "annual_income_band": "20L+",
  "document_type": "VOTER_ID",
  "document_verified": true,
  "phone_verified": true,
  "address_verified": true,
  "pep_status": false
}
```

---

## Accounts

> IMPORTANT: account IDs have an `ACC-` prefix. Use `ACC-C009001507`, not `C009001507`.

### Get an account
```
GET /accounts/{account_id}
```
Example: `GET /accounts/ACC-C009001507`
```json
{
  "account_id": "ACC-C009001507",
  "customer_id": "C009001507",
  "account_type": "SAVINGS",
  "status": "ACTIVE",
  "opening_date": "2022-03-11",
  "current_balance": 128627.91
}
```

### Get an account's transactions
```
GET /accounts/{account_id}/transactions
```
Returns an array of transaction objects (newest first).

---

## Transactions

### List transactions
```
GET /transactions/all
GET /transactions/all?limit=50
GET /transactions/all?offset=100&limit=50
GET /transactions/all?customer_id=C009001507
```
By default returns ALL ~9,991 transactions. `limit` is optional.
```json
{
  "total": 9991,
  "limit": null,
  "offset": 0,
  "returned": 9991,
  "transactions": [
    {
      "transaction_id": "TX009955",
      "step": 129730,
      "type": "TRANSFER",
      "amount": 781075.61,
      "nameOrig": "C009001507",
      "oldbalanceOrg": 3539135.98,
      "newbalanceOrig": 2758060.37,
      "nameDest": "C777000001",
      "oldbalanceDest": 0,
      "newbalanceDest": 0,
      "isFraud": 0,
      "isFlaggedFraud": 1,
      "customer_id": "C009001507",
      "account_id": "ACC-C009001507",
      "event_time": "2026-10-30T11:10:00",
      "destination_type": "ACCOUNT",
      "is_scenario_trigger": false,
      "device_id": null
    }
  ]
}
```
> Tip for the frontend: request a page (`?limit=100`) for tables; the full 9,991
> array is ~4 MB. Do NOT open the full response in Swagger UI — it crashes the
> browser renderer (use fetch/axios or a page limit).

### Submit a transaction (runs the rule engine → may create an alert)
```
GET /transactions?type=TRANSFER&amount=900000&customer_id=C009001507&account_id=ACC-C009001507&nameDest=CNEW999&destination_type=ACCOUNT
```
Required query params: `type`, `amount`, `customer_id`, `account_id`, `nameDest`, `destination_type`.
Optional: `transaction_id`, `event_time`, `is_scenario_trigger`, `device_id`.

Response:
```json
{
  "transaction_id": "TX1A2B3C4D",
  "status": "accepted",
  "alert_generated": true,
  "alert_id": "ALT7366A89F",
  "risk_score": 0.85,
  "severity": "HIGH",
  "signals": [
    { "type": "AMOUNT_DEVIATION", "weight": 0.3, "detail": "…" },
    { "type": "NEW_BENEFICIARY", "weight": 0.15, "detail": "…" }
  ]
}
```
If a rule fires (`alert_generated: true`), a NEW_ALERT is also pushed over the WebSocket.

---

## Alerts (the "flags")

### List all alerts
```
GET /alerts
GET /alerts?status=OPEN         (OPEN | INVESTIGATING | RESOLVED | ESCALATED)
```
```json
[
  {
    "alert_id": "ALT0001",
    "transaction_id": "TX009955",
    "customer_id": "C009001507",
    "alert_type": "HIGH_VALUE_NEW_BENEFICIARY",
    "severity": "HIGH",
    "status": "OPEN",
    "scenario": null,
    "created_at": null
  }
]
```

### Get a single alert
```
GET /alerts/{alert_id}
```
Example: `GET /alerts/ALT0001`

---

## Cases

### List all cases
```
GET /cases
```
```json
[
  {
    "case_id": "CASE0001",
    "customer_id": "C009001507",
    "alert_id": "ALT0001",
    "case_type": "HIGH_VALUE_NEW_BENEFICIARY",
    "status": "OPEN",
    "disposition": "PENDING",
    "investigation_note": "…"
  }
]
```

### Get a single case
```
GET /cases/{case_id}
```
Example: `GET /cases/CASE0001`

---

## Investigation context (primary FRAB endpoint — one call, everything)

```
GET /investigation/{alert_id}
```
Example: `GET /investigation/ALT0001`
```json
{
  "alert": { … },
  "customer": { … },
  "account": { … },
  "kyc": { … },
  "trigger_transaction": { … },
  "transaction_history": [ … ],
  "historical_statistics": {
    "historical_average": 135864.97,
    "historical_median": 88225.29,
    "historical_max": 781075.61,
    "historical_transaction_count": 34,
    "historical_beneficiary_count": 13,
    "note": "Calculated from customer transactions excluding the trigger transaction"
  },
  "beneficiaries": [ … ],
  "related_transactions": [ … ],
  "previous_cases": [ … ]
}
```

---

## Real-time alerts (WebSocket)

```
WS /ws/alerts
```
Connect once; the server pushes a message every time a transaction generates an alert:
```json
{ "event": "NEW_ALERT", "alert_id": "ALT…", "customer_id": "C009…", "severity": "HIGH" }
```
Frontend example:
```js
const ws = new WebSocket("ws://localhost:8000/ws/alerts");
ws.onmessage = (e) => {
  const evt = JSON.parse(e.data);   // { event, alert_id, customer_id, severity }
  // refresh the alerts list / show a toast
};
```
If you prefer not to use WebSockets, poll `GET /alerts?status=OPEN` on an interval instead.

---

## API docs (auto-generated)
```
GET /docs          Swagger UI
GET /openapi.json  OpenAPI schema (import into Postman / codegen)
```

---

# VOICE ESCALATION API

Base URL: `http://localhost:8021` (local) or the voice Cloud Run URL.

## Health
```
GET /health
```
```json
{ "status": "ok", "service": "voice-escalation-agent" }
```

## Start a voice escalation call
```
POST /api/voice/escalate
Content-Type: application/json
```
Body:
```json
{ "case_id": "CASE0001", "recipient_phone": "+919876543210" }
```
Response:
```json
{
  "call_id": "VCALL-1A2B3C4D",
  "case_id": "CASE0001",
  "status": "CALLING",
  "recipient_masked": "+91......3210",
  "vapi_call_id": "…",
  "message": "Outbound call initiated for case CASE0001"
}
```

## Get call status
```
GET /api/voice/calls/{call_id}
```
```json
{
  "call_id": "VCALL-1A2B3C4D",
  "case_id": "CASE0001",
  "status": "COMPLETED",
  "recipient_masked": "+91......3210",
  "vapi_call_id": "…",
  "started_at": "…",
  "ended_at": "…",
  "duration_seconds": 134,
  "duration_display": "02:14"
}
```
Status values: `REQUESTED → CALLING → CONNECTED → COMPLETED` (or `FAILED` / `NO_ANSWER`).

## Audit trail (for Case Book Page 08)
```
GET /api/voice/audit
GET /api/voice/audit?case_id=CASE0001
GET /api/voice/audit/{case_id}
```
```json
[
  {
    "call_id": "VCALL-1A2B3C4D",
    "case_id": "CASE0001",
    "type": "VOICE_ESCALATION",
    "status": "COMPLETED",
    "timestamp": "…Z",
    "recipient_masked": "+91......3210",
    "vapi_call_id": "…",
    "duration_seconds": 134,
    "summary": "Investigation summary delivered. Recipient acknowledged."
  }
]
```

## Vapi webhook (backend-only, not called by frontend)
```
POST /api/voice/webhook
```

---

# Quick frontend integration notes

1. **CORS is already enabled.** If the frontend runs on a port other than 3000/5173/8080,
   set `CORS_ALLOWED_ORIGINS` on the bank + voice services to include it.
2. **Account IDs need the `ACC-` prefix.** Customer `C009001507` → account `ACC-C009001507`.
3. **Alerts = flags.** Poll `GET /alerts` or subscribe to `WS /ws/alerts`.
4. **One investigation call** (`GET /investigation/{alert_id}`) returns all evidence — no need to
   make many separate requests.
5. **Runtime-generated alerts are in-memory** — they show up immediately but reset on server
   restart. The 10 seed alerts (ALT0001–ALT0010) always exist.
6. **Real IDs to test with:** customers `C009001507`, `C009000137`; alerts `ALT0001`–`ALT0010`;
   cases `CASE0001`–`CASE0010`.

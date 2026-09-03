# Synthetic Bank Backend

A demo-ready fraud detection backend for FRAB (Fraud Risk Analysis Backend).
Ingests transactions, runs a rule engine, creates alerts, and serves a consolidated investigation context to FRAB via a single GET endpoint.

---

## 1. Architecture

```
Simulator (run_simulator.py)
  └─► GET /transactions  (FastAPI)
        └─► Validate customer / account
        └─► Store transaction (in-memory / Firestore)
        └─► Rule Engine  (AnomalyDetector)
              └─► Alert created  →  stored
              └─► WebSocket broadcast  →  frontend
  └─► GET /investigation/{alert_id}  ◄── FRAB primary endpoint
        └─► alert + customer + account + KYC
        └─► trigger transaction
        └─► transaction history  (trigger excluded from statistics)
        └─► historical statistics  (live-calculated, §27.2)
        └─► beneficiaries + related transactions + previous cases
```

All endpoints are **GET only** — no POST, PUT, or DELETE.
Alerts originate exclusively from backend transaction processing.

---

## 2. Prerequisites

| Tool | Minimum version |
|------|----------------|
| Python | 3.11 |
| pip | 23 |
| Google Cloud SDK (`gcloud`) | latest |
| Docker | 24 |
| Git | 2.40 |

---

## 3. Local Setup

```bash
git clone <repository-url>
cd synthetic-bank

# Create and activate virtual environment
python -m venv .venv
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\activate
```

**Linux / macOS:**
```bash
source .venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

---

## 4. Environment Variables

Copy the example file and edit it:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLOUD_PROJECT` | For Firestore | GCP project ID |
| `FIRESTORE_DATABASE` | For Firestore | Database name, default `(default)` |
| `USE_FIRESTORE` | No | Set `true` to enable Firestore. Default `false` (CSV-only) |
| `PORT` | No | Server port. Default `8000`. Cloud Run sets this automatically |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated allowed origins. Default `http://localhost:3000,http://localhost:5173` |

For local development without Firestore, leave `USE_FIRESTORE=false`. The backend runs entirely from CSV files.

---

## 5. Firestore Setup

1. Create or identify your GCP project.
2. Enable the Firestore API in the GCP console.
3. Create a Firestore database (Native mode) — name it `(default)` or set `FIRESTORE_DATABASE` to your chosen name.
4. For local use, authenticate with Application Default Credentials:

```bash
gcloud auth application-default login
```

5. Set environment variables:

```bash
export GOOGLE_CLOUD_PROJECT=your-project-id
export USE_FIRESTORE=true
```

---

## 6. Dataset Seeding

Seed all collections from the finalized CSV dataset:

```bash
USE_FIRESTORE=true GOOGLE_CLOUD_PROJECT=your-project-id python scripts/seed_firestore.py
```

Seed specific collections only:

```bash
USE_FIRESTORE=true GOOGLE_CLOUD_PROJECT=your-project-id \
    python scripts/seed_firestore.py --collections customers accounts alerts
```

Preview counts without writing:

```bash
python scripts/seed_firestore.py --dry-run
```

Collections seeded:

| Collection | Document ID | Approx. count |
|-----------|-------------|--------------|
| `customers` | customer_id | ≈ 300 |
| `accounts` | account_id | ≈ 300 |
| `kyc_profiles` | customer_id | ≈ 300 |
| `behaviour_baseline` | customer_id | ≈ 300 |
| `beneficiaries` | customer_id + beneficiary_id | ≈ 1 105 |
| `transactions` | transaction_id | ≈ 72 (scenario feed) |
| `alerts` | alert_id | 10 |
| `cases` | case_id | 10 |
| `scenarios` | scenario_id | 10 |

The seeder is idempotent — safe to run multiple times.

---

## 7. Firestore Validation

After seeding, verify counts and cross-references:

```bash
USE_FIRESTORE=true GOOGLE_CLOUD_PROJECT=your-project-id python scripts/validate_firestore.py
```

The script prints `[PASS]` or `[FAIL]` for every check and exits with code 1 if any check fails.

---

## 8. Starting the Backend

```bash
uvicorn app.main:app --reload
```

The server starts on `http://localhost:8000` by default.

Interactive API docs: `http://localhost:8000/docs`

Health check:

```bash
curl http://localhost:8000/health
# → {"status":"ok","service":"synthetic-bank"}
```

---

## 9. API Testing

All endpoints are GET only.

```bash
# Health
curl http://localhost:8000/health

# Customer
curl http://localhost:8000/customers/C009001507

# Customer KYC
curl http://localhost:8000/customers/C009001507/kyc

# Account
curl http://localhost:8000/accounts/ACC-C009001507

# Alerts (all)
curl http://localhost:8000/alerts

# Alerts (open only)
curl "http://localhost:8000/alerts?status=OPEN"

# Single alert
curl http://localhost:8000/alerts/ALT0001

# Cases
curl http://localhost:8000/cases
curl http://localhost:8000/cases/CASE0001

# Investigation context (primary FRAB endpoint)
curl http://localhost:8000/investigation/ALT0001

# Submit a transaction
curl "http://localhost:8000/transactions?transaction_id=TXTEST&type=TRANSFER&amount=500000&customer_id=C009001507&account_id=ACC-C009001507&nameDest=C999999999&destination_type=ACCOUNT&event_time=2026-10-30T12:00:00"
```

---

## 10. Simulator

The simulator reads `data/seed/transactions.csv` and replays transactions through the HTTP API.  It never writes directly to Firestore.

```bash
# Single scenario
python scripts/run_simulator.py --base-url http://localhost:8000 --scenario SCN01 --delay 2

# All scenarios
python scripts/run_simulator.py --base-url http://localhost:8000 --all --delay 2

# Full feed (no scenario filter)
python scripts/run_simulator.py --base-url http://localhost:8000 --delay 1

# Preview URLs without sending
python scripts/run_simulator.py --base-url http://localhost:8000 --all --dry-run
```

Flags:

| Flag | Description |
|------|-------------|
| `--base-url` | Backend URL (default: `http://localhost:8000`) |
| `--scenario` | Run a specific scenario: `SCN01` … `SCN10` |
| `--all` | Run all scenarios (full feed) |
| `--delay` | Seconds between requests (default: `1.0`) |
| `--dry-run` | Print request URLs without sending |

---

## 11. Scenarios SCN01–SCN10

Each scenario exercises one fraud detection pattern.  Run the simulator, then call `GET /investigation/{alert_id}` with the generated alert ID.

| Scenario | Type | Trigger TX | Alert | Customer |
|----------|------|-----------|-------|---------|
| SCN01 | HIGH_VALUE_NEW_BENEFICIARY | TX009955 | ALT0001 | C009001507 |
| SCN02 | VELOCITY_SPIKE | TX009963 | ALT0002 | C009005617 |
| SCN03 | STRUCTURING_PATTERN | TX009967 | ALT0003 | C009009727 |
| SCN04 | BEHAVIOUR_DEVIATION | TX009968 | ALT0004 | C009013837 |
| SCN05 | NEW_BENEFICIARY | TX009969 | ALT0005 | C009017947 |
| SCN06 | KYC_MISMATCH | TX009970 | ALT0006 | C009022057 |
| SCN07 | MULE_PATTERN | TX009971 | ALT0007 | C009026167 |
| SCN08 | REPEATED_CASHOUT | TX009981 | ALT0008 | C009030277 |
| SCN09 | CROSS_ACCOUNT_BURST | TX009982 | ALT0009 | C009034387 |
| SCN10 | FALSE_POSITIVE_HISTORY | TX009991 | ALT0010 | C009038497 |

### SCN10 — False Positive

SCN10 is the false-positive demonstration scenario.  Run it as:

```bash
python scripts/run_simulator.py --base-url http://localhost:8000 --scenario SCN10 --delay 2
```

Then verify the investigation context:

```bash
curl http://localhost:8000/investigation/ALT0010
```

Expected response structure includes `historical_statistics` with `historical_average`, `historical_median`, `historical_max`, `historical_transaction_count`, and `historical_beneficiary_count` — all calculated excluding TX009991.  The backend does **not** hardcode a recommendation; FRAB makes the final decision.

---

## 12. Cloud Run Deployment

### Prerequisites

- GCP project with Artifact Registry repository `frab-repo` (or create one).
- Cloud Run API enabled.
- Service account attached to the Cloud Run service with Firestore read/write permissions.

### Build and push image

Replace `REGION` and `PROJECT_ID` with your actual values:

```bash
gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/frab-repo/synthetic-bank-api \
  .
```

### Deploy

```bash
gcloud run deploy synthetic-bank-api \
  --image REGION-docker.pkg.dev/PROJECT_ID/frab-repo/synthetic-bank-api \
  --region REGION \
  --platform managed \
  --set-env-vars GOOGLE_CLOUD_PROJECT=PROJECT_ID \
  --set-env-vars FIRESTORE_DATABASE='(default)' \
  --set-env-vars USE_FIRESTORE=true \
  --set-env-vars CORS_ALLOWED_ORIGINS=https://your-frontend.run.app
```

Cloud Run automatically injects `PORT`; do not set it manually.

### Verify deployment

After obtaining the Cloud Run URL:

```bash
curl https://YOUR_CLOUD_RUN_URL/health
# → {"status":"ok","service":"synthetic-bank"}

curl https://YOUR_CLOUD_RUN_URL/alerts
curl https://YOUR_CLOUD_RUN_URL/investigation/ALT0001
```

---

## 13. API Endpoints

All endpoints are **GET only**.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/customers/{customer_id}` | Customer record |
| GET | `/customers/{customer_id}/kyc` | KYC profile |
| GET | `/accounts/{account_id}` | Account record |
| GET | `/accounts/{account_id}/transactions` | Account transaction history |
| GET | `/alerts` | List all alerts (`?status=OPEN` to filter) |
| GET | `/alerts/{alert_id}` | Single alert |
| GET | `/cases` | List all cases |
| GET | `/cases/{case_id}` | Single case |
| GET | `/investigation/{alert_id}` | Consolidated investigation context |
| GET | `/transactions/all` | List all loaded transactions, newest first |
| GET | `/transactions` | Submit transaction (all fields as query params) |
| WS  | `/ws/alerts` | Real-time alert feed |
| GET | `/docs` | Interactive API documentation (Swagger UI) |
| GET | `/openapi.json` | OpenAPI schema |

### GET /transactions — required query parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | TRANSFER, PAYMENT, DEBIT, CASH_OUT, CASH_IN |
| `amount` | float | Transaction amount |
| `customer_id` | string | e.g. C009001507 |
| `account_id` | string | e.g. ACC-C009001507 |
| `nameDest` | string | Destination account or merchant ID |
| `destination_type` | string | ACCOUNT or MERCHANT |

Optional: `transaction_id`, `event_time`, `is_scenario_trigger`, `device_id`, `stream_order`, `emit_delay_ms`.

### GET /investigation/{alert_id} — response shape

```json
{
  "alert": {},
  "customer": {},
  "account": {},
  "kyc": {},
  "trigger_transaction": {},
  "transaction_history": [],
  "historical_statistics": {
    "historical_average": 0.0,
    "historical_median": 0.0,
    "historical_max": 0.0,
    "historical_transaction_count": 0,
    "historical_beneficiary_count": 0,
    "note": "Calculated from customer transactions excluding the trigger transaction"
  },
  "beneficiaries": [],
  "related_transactions": [],
  "previous_cases": []
}
```

---

## 14. FRAB Integration

FRAB uses one primary endpoint:

```
GET /investigation/{alert_id}
```

Example:

```
GET https://YOUR_CLOUD_RUN_URL/investigation/ALT0001
```

The response delivers everything FRAB needs in a single call:

- Alert metadata (severity, type, status, scenario)
- Customer profile and KYC
- Account details
- The transaction that triggered the alert
- Historical transaction context (trigger excluded from statistics per §27.2)
- Live-calculated baseline statistics
- Known beneficiaries
- Other transactions to the same destination (mule / burst evidence)
- Previous cases for the same customer

FRAB is responsible for the investigation decision.  The backend supplies evidence only and does not hardcode recommendations.

### Real-time alerts (WebSocket)

Connect to `ws://HOST/ws/alerts` to receive alert events as they are created:

```json
{
  "event": "NEW_ALERT",
  "alert_id": "ALT...",
  "customer_id": "C009...",
  "severity": "HIGH"
}
```

If WebSocket is not available, poll `GET /alerts?status=OPEN` on a regular interval.

### End-to-end demo flow

```
1. Start backend:   uvicorn app.main:app --reload
2. Run simulator:   python scripts/run_simulator.py --scenario SCN01 --delay 2
3. Retrieve alert:  GET /alerts/ALT0001
4. Investigate:     GET /investigation/ALT0001
5. FRAB reasoning → FRAB makes final decision (ESCALATE / MONITOR / CLOSE)
```

For SCN10 (false positive):

```
1. python scripts/run_simulator.py --scenario SCN10 --delay 2
2. GET /investigation/ALT0010
3. historical_statistics shows prior high-value transfers to same beneficiary
4. FRAB reviews evidence → decides CLOSE_FALSE_POSITIVE or MONITOR
```

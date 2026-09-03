import os

# ── Data directory ─────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "seed", "FRAB_DEMO_READY_DATASET"
)

# ── CSV_MAP: logical name → actual filename ────────────────────────────────────
CSV_MAP = {
    "customers":          "customers.csv",
    "accounts":           "accounts.csv",
    "alerts":             "alerts.csv",
    "behaviour_baseline": "behaviour_baseline.csv",
    "beneficiaries":      "beneficiaries.csv",
    "cases":              "cases.csv",
    "kyc_profiles":       "kyc_profiles.csv",
    "merchants":          "merchants.csv",
    "scenarios":          "demo_runs.csv",
    "transactions":       "transactions.csv",
}

# ── Google Cloud / Firestore ───────────────────────────────────────────────────
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
FIRESTORE_DATABASE   = os.environ.get("FIRESTORE_DATABASE", "(default)")

# Legacy alias kept for backward compatibility with firestore_service.py
GCP_PROJECT = GOOGLE_CLOUD_PROJECT or os.environ.get("GCP_PROJECT", "")

USE_FIRESTORE = os.environ.get("USE_FIRESTORE", "false").lower() == "true"

FIRESTORE_EMULATOR_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST")

# ── Server ─────────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", "8000"))

# ── CORS ───────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins.
# http://localhost:8080 and http://127.0.0.1:8080 allow a local frontend
# running on port 8080 to call the Cloud Run backend without CORS errors.
# Override at deployment time via the CORS_ALLOWED_ORIGINS env var, e.g.:
#   CORS_ALLOWED_ORIGINS=https://my-frontend.run.app,http://localhost:8080
_raw_origins = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://127.0.0.1:8080",
)
CORS_ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# ── Rule-engine weights ────────────────────────────────────────────────────────
RISK_WEIGHTS = {
    "AMOUNT_DEVIATION":       0.30,
    "VELOCITY_SPIKE":         0.15,
    "NEW_DEVICE":             0.20,
    "NEW_BENEFICIARY":        0.15,
    "KYC_BEHAVIOUR_MISMATCH": 0.20,
}

# A transaction is flagged HIGH (and an alert is created) at or above this score.
# Calibrated to 0.60 so genuine scenario triggers fire on the finalized dataset,
# which carries no device_id column (NEW_DEVICE cannot contribute a signal).
# A high-value transfer to a new beneficiary that also mismatches KYC scores
# 0.30 + 0.15 + 0.20 = 0.65 and must alert; a normal merchant payment scores
# only 0.15 and must not.
HIGH_SEVERITY_THRESHOLD = 0.60

# A transaction triggers VELOCITY_SPIKE when >= VELOCITY_THRESHOLD other
# transactions for the same customer fall within VELOCITY_WINDOW_SECONDS.
VELOCITY_WINDOW_SECONDS = 600
VELOCITY_THRESHOLD      = 5

import os

# ── Data directory ─────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "seed")

# ── CSV_MAP: logical name → actual filename ────────────────────────────────────
# The filenames on disk are historically misnamed; this map corrects the mapping
# so every loader always opens the right file.
CSV_MAP = {
    "customers":          "demo_runs.csv",          # customer records
    "accounts":           "alerts.csv",             # account records
    "alerts":             "behaviour_baseline.csv", # alert records
    "behaviour_baseline": "beneficiaries.csv",      # behaviour baseline records
    "beneficiaries":      "cases.csv",              # beneficiary records
    "cases":              "customers.csv",           # case records
    "kyc_profiles":       "merchants.csv",           # KYC profile records
    "scenarios":          "kyc_profiles.csv",        # scenario records
    "transactions":       "transactions.csv",        # transaction records
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
# Comma-separated list of allowed origins, e.g.
#   CORS_ALLOWED_ORIGINS=http://localhost:5173,https://my-frontend.run.app
_raw_origins = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173",
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

HIGH_SEVERITY_THRESHOLD = 0.70

# A transaction triggers VELOCITY_SPIKE when ≥ VELOCITY_THRESHOLD other
# transactions for the same customer fall within VELOCITY_WINDOW_SECONDS.
VELOCITY_WINDOW_SECONDS = 600
VELOCITY_THRESHOLD      = 5

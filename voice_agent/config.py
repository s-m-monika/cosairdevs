import os

# ── Vapi ───────────────────────────────────────────────────────────────────────
# Get these from https://dashboard.vapi.ai
VAPI_API_KEY       = os.environ.get("VAPI_API_KEY", "")
VAPI_ASSISTANT_ID  = os.environ.get("VAPI_ASSISTANT_ID", "")
VAPI_PHONE_NUMBER_ID = os.environ.get("VAPI_PHONE_NUMBER_ID", "")

VAPI_BASE_URL = "https://api.vapi.ai"

# ── Twilio (used only when importing number into Vapi — not called directly) ──
TWILIO_ACCOUNT_SID  = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN   = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")  # e.g. +12015551234

# ── FRAB backend ───────────────────────────────────────────────────────────────
# URL of the synthetic bank / FRAB investigation API
# Local dev: http://localhost:8000
# Production: https://YOUR-CLOUD-RUN-URL
FRAB_BACKEND_URL = os.environ.get("FRAB_BACKEND_URL", "http://localhost:8000")

# ── Service ────────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", "8001"))

# Webhook URL that Vapi will POST call-status events to.
# Must be a publicly reachable URL (use ngrok locally, Cloud Run URL in prod).
# Example: https://voice-agent-xyz.run.app/api/voice/webhook
VAPI_WEBHOOK_URL = os.environ.get("VAPI_WEBHOOK_URL", "")

# ── CORS ───────────────────────────────────────────────────────────────────────
_raw = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://127.0.0.1:8080",
)
CORS_ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw.split(",") if o.strip()]

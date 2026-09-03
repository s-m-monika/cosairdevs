from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Request / Response models ──────────────────────────────────────────────────

class EscalateRequest(BaseModel):
    """Body sent by the FRAB frontend to trigger a voice escalation call."""
    case_id: str = Field(..., description="FRAB case ID, e.g. CASE0001 or FRAB-00000091")
    recipient_phone: str = Field(
        ...,
        description="E.164 phone number of the analyst to call, e.g. +919876543210",
    )


class EscalateResponse(BaseModel):
    """Returned immediately when the call has been queued with Vapi."""
    call_id: str
    case_id: str
    status: str                   # REQUESTED | CALLING | CONNECTED | COMPLETED | FAILED
    recipient_masked: str         # +91......1234
    vapi_call_id: Optional[str] = None
    message: str = "Voice escalation call initiated"


class CallStatusResponse(BaseModel):
    call_id: str
    case_id: str
    status: str
    recipient_masked: str
    vapi_call_id: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    duration_display: Optional[str] = None   # e.g. "02:14"


# ── Audit record ───────────────────────────────────────────────────────────────

class AuditEvent(BaseModel):
    """Persisted after a call completes or fails."""
    call_id: str
    case_id: str
    type: str = "VOICE_ESCALATION"
    status: str
    timestamp: str                 # ISO-8601 UTC
    recipient_masked: str          # +91••••••1234  — never store full number
    vapi_call_id: Optional[str] = None
    duration_seconds: Optional[int] = None
    summary: Optional[str] = None  # Brief text from Vapi end-of-call report


# ── Internal call record (stored in CallStore) ─────────────────────────────────

class CallStatus(str, Enum):
    REQUESTED = "REQUESTED"
    CALLING   = "CALLING"
    CONNECTED = "CONNECTED"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    NO_ANSWER = "NO_ANSWER"


class CallRecord(BaseModel):
    call_id: str
    case_id: str
    recipient_phone: str           # full number — server-side only, never returned
    recipient_masked: str          # returned to UI
    vapi_call_id: Optional[str] = None
    status: CallStatus = CallStatus.REQUESTED
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    audit_summary: Optional[str] = None
    case_context: Optional[dict[str, Any]] = None   # snapshot used for the call


# ── Vapi webhook payload (subset we care about) ────────────────────────────────

class VapiWebhookPayload(BaseModel):
    """
    Vapi sends POST callbacks to our /api/voice/webhook endpoint.
    We only parse the fields we need; extra fields are ignored.
    """
    message: Optional[dict[str, Any]] = None

    model_config = {"extra": "allow"}

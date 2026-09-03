from __future__ import annotations

"""
FRAB Voice Escalation Agent — FastAPI service
=============================================

Endpoints
---------
POST /api/voice/escalate
    Accepts caseId + recipientPhone, fetches FRAB investigation,
    initiates Vapi outbound call, returns call_id and status.

GET  /api/voice/calls/{call_id}
    Returns current call status + duration for the Case Book UI.

GET  /api/voice/audit
    Returns full audit trail (optionally filtered by case_id).

GET  /api/voice/audit/{case_id}
    Returns audit events for a single case.

POST /api/voice/webhook
    Receives Vapi call-status events (call-started, call-ended, etc.)
    and updates the call record accordingly.

GET  /health
    Service health check.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from voice_agent.call_store import get_store
from voice_agent.config import CORS_ALLOWED_ORIGINS
from voice_agent.frab_client import get_case_context
from voice_agent.models import (
    AuditEvent,
    CallStatusResponse,
    EscalateRequest,
    EscalateResponse,
    VapiWebhookPayload,
)
from voice_agent.vapi_client import create_outbound_call

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Voice Escalation Agent starting up.")
    yield
    logger.info("Voice Escalation Agent shutting down.")


app = FastAPI(
    title="FRAB Voice Escalation Agent",
    description=(
        "Isolated service that fetches a completed FRAB investigation, "
        "initiates a Vapi outbound call to an analyst, and records an audit trail. "
        "Does NOT modify the synthetic bank backend or investigation agents."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Operations"])
def health() -> dict:
    """Returns service health. Expected: {"status":"ok","service":"voice-escalation-agent"}"""
    return {"status": "ok", "service": "voice-escalation-agent"}


# ── POST /api/voice/escalate ───────────────────────────────────────────────────

@app.post(
    "/api/voice/escalate",
    response_model=EscalateResponse,
    summary="Initiate a voice escalation call",
    description=(
        "Fetches the completed FRAB investigation for caseId, "
        "builds a dynamic call context, and initiates a Vapi outbound call "
        "to the recipient phone number. Returns call_id and initial status."
    ),
    tags=["Voice Escalation"],
)
async def escalate(body: EscalateRequest) -> EscalateResponse:
    store = get_store()

    # 1. Create pending call record immediately so the UI can show REQUESTED
    record = store.create_call(
        case_id=body.case_id,
        recipient_phone=body.recipient_phone,
    )

    # 2. Fetch FRAB case context — voice agent only reads, never writes FRAB
    try:
        case_context = await get_case_context(body.case_id)
    except Exception as exc:
        store.set_failed(record.call_id, summary=f"FRAB fetch failed: {exc}")
        logger.error("Failed to fetch case context for %s: %s", body.case_id, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Could not retrieve case {body.case_id} from FRAB backend: {exc}",
        )

    if case_context is None:
        store.set_failed(record.call_id, summary="Case not found in FRAB")
        raise HTTPException(
            status_code=404,
            detail=f"Case {body.case_id} not found in FRAB backend.",
        )

    # Attach context snapshot to the record (used for audit / re-inspection)
    record.case_context = case_context

    # 3. Initiate the Vapi outbound call
    try:
        vapi_response = await create_outbound_call(
            recipient_phone=body.recipient_phone,
            case_context=case_context,
        )
    except Exception as exc:
        store.set_failed(record.call_id, summary=f"Vapi call creation failed: {exc}")
        logger.error("Vapi call failed for case %s: %s", body.case_id, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Vapi outbound call failed: {exc}",
        )

    # 4. Update record to CALLING with the Vapi call ID
    vapi_call_id = vapi_response.get("id", "")
    store.set_calling(record.call_id, vapi_call_id=vapi_call_id)

    logger.info(
        "Escalation call initiated: call_id=%s vapi_call_id=%s case=%s",
        record.call_id, vapi_call_id, body.case_id,
    )

    return EscalateResponse(
        call_id=record.call_id,
        case_id=body.case_id,
        status="CALLING",
        recipient_masked=record.recipient_masked,
        vapi_call_id=vapi_call_id,
        message=f"Outbound call initiated for case {body.case_id}",
    )


# ── GET /api/voice/calls/{call_id} ─────────────────────────────────────────────

@app.get(
    "/api/voice/calls/{call_id}",
    response_model=CallStatusResponse,
    summary="Get current status of a voice call",
    tags=["Voice Escalation"],
)
def get_call_status(call_id: str) -> CallStatusResponse:
    store = get_store()
    record = store.get_call(call_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")

    duration_display: Optional[str] = None
    if record.duration_seconds is not None:
        m, s = divmod(record.duration_seconds, 60)
        duration_display = f"{m:02d}:{s:02d}"

    return CallStatusResponse(
        call_id=record.call_id,
        case_id=record.case_id,
        status=record.status.value,
        recipient_masked=record.recipient_masked,
        vapi_call_id=record.vapi_call_id,
        started_at=record.started_at,
        ended_at=record.ended_at,
        duration_seconds=record.duration_seconds,
        duration_display=duration_display,
    )


# ── GET /api/voice/audit ───────────────────────────────────────────────────────

@app.get(
    "/api/voice/audit",
    response_model=list[AuditEvent],
    summary="List all audit events (optionally filter by case_id)",
    tags=["Audit"],
)
def list_audit(
    case_id: Optional[str] = Query(
        default=None,
        description="Filter audit events by FRAB case ID",
    )
) -> list[AuditEvent]:
    store = get_store()
    return store.get_audit(case_id=case_id)


@app.get(
    "/api/voice/audit/{case_id}",
    response_model=list[AuditEvent],
    summary="List audit events for a specific case",
    tags=["Audit"],
)
def get_case_audit(case_id: str) -> list[AuditEvent]:
    store = get_store()
    events = store.get_audit(case_id=case_id)
    if not events:
        raise HTTPException(
            status_code=404,
            detail=f"No audit events found for case {case_id}",
        )
    return events


# ── POST /api/voice/webhook ────────────────────────────────────────────────────

@app.post(
    "/api/voice/webhook",
    summary="Vapi webhook — receives call-status events",
    description=(
        "Vapi POSTs call lifecycle events here. "
        "Updates internal call status and writes the audit record on completion. "
        "Must be publicly reachable (set VAPI_WEBHOOK_URL in your env)."
    ),
    tags=["Webhook"],
)
async def vapi_webhook(payload: VapiWebhookPayload) -> dict:
    """
    Vapi webhook event types we handle:
      call-started   → CONNECTED
      call-ended     → COMPLETED (with duration + summary)
      call-failed    → FAILED
      no-answer      → NO_ANSWER

    Vapi sends the event inside payload.message.type
    """
    store = get_store()
    message = payload.message or {}
    event_type: str = message.get("type", "")
    call_obj: dict  = message.get("call", {}) or {}
    vapi_call_id: str = call_obj.get("id", "") or message.get("callId", "")

    logger.info("Vapi webhook: type=%s vapi_call_id=%s", event_type, vapi_call_id)

    if not vapi_call_id:
        # Some Vapi events use a flat structure
        vapi_call_id = message.get("id", "")

    record = store.find_by_vapi_id(vapi_call_id) if vapi_call_id else None

    if record is None:
        # Unknown call — ack and move on
        logger.warning("Webhook for unknown vapi_call_id=%s", vapi_call_id)
        return {"received": True}

    if event_type in ("call-started", "callStarted"):
        store.set_connected(record.call_id)

    elif event_type in ("call-ended", "callEnded", "end-of-call-report"):
        # Extract duration from Vapi end-of-call report
        duration_s: Optional[int] = None
        summary_text: Optional[str] = None

        report = message.get("endedReason") or ""

        # Duration in seconds from Vapi
        raw_duration = (
            message.get("durationSeconds")
            or call_obj.get("durationSeconds")
        )
        if raw_duration is not None:
            try:
                duration_s = int(float(raw_duration))
            except (ValueError, TypeError):
                pass

        # Summary / transcript snippet
        summary_text = (
            message.get("summary")
            or message.get("transcript")
            or (f"Call ended: {report}" if report else None)
            or "Investigation summary delivered."
        )

        store.set_completed(
            record.call_id,
            duration_seconds=duration_s,
            summary=summary_text,
        )
        logger.info(
            "Call completed: call_id=%s duration=%ss",
            record.call_id, duration_s,
        )

    elif event_type in ("call-failed", "callFailed"):
        store.set_failed(record.call_id, summary="Call failed via Vapi webhook")

    elif event_type in ("no-answer", "noAnswer"):
        from voice_agent.models import CallStatus
        store.set_failed(record.call_id, status=CallStatus.NO_ANSWER, summary="No answer")

    return {"received": True}

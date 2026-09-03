from __future__ import annotations

"""
In-memory call store.

Tracks every call from REQUESTED through COMPLETED/FAILED and stores audit
events.  Replace with a database for production.
"""

import uuid
from datetime import datetime
from typing import Optional

from voice_agent.models import AuditEvent, CallRecord, CallStatus


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _mask_phone(number: str) -> str:
    """
    Mask phone number for display.
    +919876543210  →  +91......3210
    Keeps country code prefix and last 4 digits only.
    """
    if not number:
        return "******"
    # Keep up to 3 chars of country code prefix + mask middle + last 4
    if number.startswith("+"):
        prefix = number[:3]          # e.g. "+91"
        suffix = number[-4:]         # last 4 digits
        return f"{prefix}{'.' * 6}{suffix}"
    return number[:2] + "." * 6 + number[-4:]


def _duration_display(seconds: Optional[int]) -> Optional[str]:
    if seconds is None:
        return None
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


class CallStore:
    def __init__(self) -> None:
        self._calls: dict[str, CallRecord] = {}
        self._audit: list[AuditEvent] = []

    # ── Create ─────────────────────────────────────────────────────────────────

    def create_call(self, case_id: str, recipient_phone: str) -> CallRecord:
        call_id = f"VCALL-{uuid.uuid4().hex[:8].upper()}"
        record = CallRecord(
            call_id=call_id,
            case_id=case_id,
            recipient_phone=recipient_phone,
            recipient_masked=_mask_phone(recipient_phone),
            status=CallStatus.REQUESTED,
        )
        self._calls[call_id] = record
        return record

    # ── Update ─────────────────────────────────────────────────────────────────

    def set_calling(self, call_id: str, vapi_call_id: str) -> None:
        rec = self._calls.get(call_id)
        if rec:
            rec.vapi_call_id = vapi_call_id
            rec.status = CallStatus.CALLING
            rec.started_at = _now()

    def set_connected(self, call_id: str) -> None:
        rec = self._calls.get(call_id)
        if rec:
            rec.status = CallStatus.CONNECTED

    def set_completed(
        self,
        call_id: str,
        duration_seconds: Optional[int] = None,
        summary: Optional[str] = None,
    ) -> None:
        rec = self._calls.get(call_id)
        if rec:
            rec.status = CallStatus.COMPLETED
            rec.ended_at = _now()
            rec.duration_seconds = duration_seconds
            rec.audit_summary = summary
            self._write_audit(rec)

    def set_failed(
        self,
        call_id: str,
        status: CallStatus = CallStatus.FAILED,
        summary: Optional[str] = None,
    ) -> None:
        rec = self._calls.get(call_id)
        if rec:
            rec.status = status
            rec.ended_at = _now()
            rec.audit_summary = summary
            self._write_audit(rec)

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_call(self, call_id: str) -> Optional[CallRecord]:
        return self._calls.get(call_id)

    def find_by_vapi_id(self, vapi_call_id: str) -> Optional[CallRecord]:
        for rec in self._calls.values():
            if rec.vapi_call_id == vapi_call_id:
                return rec
        return None

    def get_audit(self, case_id: Optional[str] = None) -> list[AuditEvent]:
        if case_id:
            return [e for e in self._audit if e.case_id == case_id]
        return list(self._audit)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _write_audit(self, rec: CallRecord) -> None:
        event = AuditEvent(
            call_id=rec.call_id,
            case_id=rec.case_id,
            type="VOICE_ESCALATION",
            status=rec.status.value,
            timestamp=rec.ended_at or _now(),
            recipient_masked=rec.recipient_masked,
            vapi_call_id=rec.vapi_call_id,
            duration_seconds=rec.duration_seconds,
            summary=rec.audit_summary or _default_summary(rec.status),
        )
        self._audit.append(event)

    def duration_display(self, call_id: str) -> Optional[str]:
        rec = self._calls.get(call_id)
        if rec:
            return _duration_display(rec.duration_seconds)
        return None


def _default_summary(status: CallStatus) -> str:
    return {
        CallStatus.COMPLETED: "Investigation summary delivered. Recipient acknowledged.",
        CallStatus.FAILED:    "Call failed to connect.",
        CallStatus.NO_ANSWER: "No answer from recipient.",
    }.get(status, "")


# Module-level singleton
_store: Optional[CallStore] = None


def get_store() -> CallStore:
    global _store
    if _store is None:
        _store = CallStore()
    return _store

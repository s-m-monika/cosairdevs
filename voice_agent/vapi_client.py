from __future__ import annotations

"""
Vapi API client — outbound call creation only.

Docs: https://docs.vapi.ai/calls/outbound-calling
"""

import logging
from typing import Any, Optional

import httpx

from voice_agent.config import (
    VAPI_API_KEY,
    VAPI_ASSISTANT_ID,
    VAPI_BASE_URL,
    VAPI_PHONE_NUMBER_ID,
    VAPI_WEBHOOK_URL,
)

logger = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json",
    }


def _build_call_context_message(case_context: dict[str, Any]) -> str:
    """
    Turn the FRAB case JSON into a concise plain-English briefing that the
    Vapi assistant will read as its first message.  No information is invented —
    only what is present in case_context is used.
    """
    case_id    = case_context.get("case_id", "Unknown")
    alert_type = case_context.get("alert_type") or case_context.get("case_type", "Unknown")
    risk_level = case_context.get("risk_level") or case_context.get("severity", "Unknown")
    risk_score = case_context.get("risk_score")
    rec        = case_context.get("recommendation") or case_context.get("disposition", "Pending")
    evidence   = case_context.get("evidence") or []
    note       = case_context.get("investigation_note") or ""

    score_str = f" (score {risk_score:.2f})" if risk_score is not None else ""

    evidence_str = ""
    if evidence:
        evidence_str = "Key evidence: " + "; ".join(str(e) for e in evidence) + ". "
    elif note:
        evidence_str = f"Investigation note: {note}. "

    return (
        f"You are calling about FRAB Case {case_id}. "
        f"Alert type: {alert_type}. "
        f"Risk level: {risk_level}{score_str}. "
        f"{evidence_str}"
        f"FRAB recommendation: {rec}. "
        f"Please summarise this investigation to the recipient and ask if they need further information."
    )


async def create_outbound_call(
    recipient_phone: str,
    case_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Initiate a Vapi outbound call.

    Returns the full Vapi call object on success.
    Raises httpx.HTTPStatusError on API errors.
    """
    if not VAPI_API_KEY:
        raise ValueError("VAPI_API_KEY is not set")
    if not VAPI_ASSISTANT_ID:
        raise ValueError("VAPI_ASSISTANT_ID is not set")
    if not VAPI_PHONE_NUMBER_ID:
        raise ValueError("VAPI_PHONE_NUMBER_ID is not set")

    context_message = _build_call_context_message(case_context)

    payload: dict[str, Any] = {
        "assistantId": VAPI_ASSISTANT_ID,
        "phoneNumberId": VAPI_PHONE_NUMBER_ID,
        "customer": {
            "number": recipient_phone,
        },
        # Override the assistant's first message with live case context.
        # This makes every call dynamic — Case 91 talks about Case 91, etc.
        "assistantOverrides": {
            "firstMessage": context_message,
        },
    }

    # Attach webhook so Vapi POSTs call-status events back to us.
    if VAPI_WEBHOOK_URL:
        payload["assistantOverrides"]["serverUrl"] = VAPI_WEBHOOK_URL

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{VAPI_BASE_URL}/call/phone",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    logger.info(
        "Vapi call created: vapi_call_id=%s recipient=%s",
        data.get("id"),
        recipient_phone[:4] + "****",
    )
    return data


async def get_call(vapi_call_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single call record from Vapi."""
    if not VAPI_API_KEY:
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{VAPI_BASE_URL}/call/{vapi_call_id}",
            headers=_headers(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

from __future__ import annotations

"""
FRAB backend client.

Fetches the completed investigation / case context from the synthetic bank
backend so the voice agent has real data to speak about.

The voice service NEVER reads from Firestore or the bank CSVs directly.
All data comes through the FRAB HTTP API.
"""

import logging
from typing import Any, Optional

import httpx

from voice_agent.config import FRAB_BACKEND_URL

logger = logging.getLogger(__name__)


def _base() -> str:
    return FRAB_BACKEND_URL.rstrip("/")


async def get_case_context(case_id: str) -> Optional[dict[str, Any]]:
    """
    Fetch a case from FRAB and build a unified context dict for the voice agent.

    Strategy:
    1. GET /cases/{case_id}               — case record (type, status, note)
    2. GET /alerts/{alert_id}             — alert linked to the case
    3. GET /investigation/{alert_id}      — full investigation context

    Returns a single merged dict, or None if the case is not found.
    """
    async with httpx.AsyncClient(timeout=20, base_url=_base()) as client:

        # 1. Case record
        case_resp = await client.get(f"/cases/{case_id}")
        if case_resp.status_code == 404:
            logger.warning("Case %s not found in FRAB backend", case_id)
            return None
        case_resp.raise_for_status()
        case_data: dict[str, Any] = case_resp.json()

        alert_id: str = case_data.get("alert_id", "")

        # 2. Alert record
        alert_data: dict[str, Any] = {}
        if alert_id:
            alert_resp = await client.get(f"/alerts/{alert_id}")
            if alert_resp.status_code == 200:
                alert_data = alert_resp.json()

        # 3. Full investigation context
        investigation: dict[str, Any] = {}
        if alert_id:
            inv_resp = await client.get(f"/investigation/{alert_id}")
            if inv_resp.status_code == 200:
                investigation = inv_resp.json()

    # Merge into a single voice-friendly context dict
    context: dict[str, Any] = {
        "case_id":            case_data.get("case_id", case_id),
        "alert_id":           alert_id,
        "case_type":          case_data.get("case_type", ""),
        "alert_type":         alert_data.get("alert_type", case_data.get("case_type", "")),
        "risk_level":         alert_data.get("severity", ""),
        "status":             case_data.get("status", ""),
        "disposition":        case_data.get("disposition", ""),
        "recommendation":     case_data.get("disposition", "PENDING"),
        "investigation_note": case_data.get("investigation_note", ""),
    }

    # Pull evidence from investigation context if available
    inv_alert = investigation.get("alert") or {}
    if inv_alert.get("expected_reason"):
        context["evidence"] = [inv_alert["expected_reason"]]

    # Historical statistics as supporting evidence
    stats = investigation.get("historical_statistics")
    if stats and stats.get("historical_transaction_count", 0) > 0:
        context["historical_stats"] = stats

    # Customer name for personalisation (never the full phone / account number)
    customer = investigation.get("customer") or {}
    if customer.get("customer_name"):
        context["customer_name"] = customer["customer_name"]

    logger.info(
        "Built case context for %s: alert=%s risk=%s recommendation=%s",
        case_id, alert_id,
        context.get("risk_level"), context.get("recommendation"),
    )
    return context

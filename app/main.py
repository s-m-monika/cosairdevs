from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ALLOWED_ORIGINS
from app.data_loader import get_store
from app.detector import AnomalyDetector
from app.investigation_service import build_investigation
from app.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    CaseRecord,
    Customer,
    InvestigationContext,
    Transaction,
    WebSocketEvent,
)
from app.websocket_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading data store…")
    get_store()
    logger.info("Data store ready.")
    yield
    logger.info("Shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Synthetic Bank API",
    description=(
        "FRAB fraud-detection backend. "
        "Provides customer data, alerts, and investigation context. "
        "All transaction submission is done via GET /transactions (query-string params)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    summary="Health check",
    tags=["Operations"],
)
def health() -> dict:
    """Returns service health status. Must return ``{"status":"ok","service":"synthetic-bank"}``."""
    return {"status": "ok", "service": "synthetic-bank"}


# ── Customers ──────────────────────────────────────────────────────────────────

@app.get(
    "/customers/{customer_id}",
    summary="Get customer by ID",
    tags=["Customers"],
    response_model=dict,
)
def get_customer(customer_id: str) -> dict:
    store = get_store()
    customer = store.get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return customer.model_dump()


@app.get(
    "/customers/{customer_id}/kyc",
    summary="Get KYC profile for a customer",
    tags=["Customers"],
    response_model=dict,
)
def get_customer_kyc(customer_id: str) -> dict:
    store = get_store()
    kyc = store.get_kyc(customer_id)
    if not kyc:
        raise HTTPException(status_code=404, detail=f"KYC not found for customer {customer_id}")
    return kyc.model_dump()


# ── Accounts ───────────────────────────────────────────────────────────────────

@app.get(
    "/accounts/{account_id}",
    summary="Get account by ID",
    tags=["Accounts"],
    response_model=dict,
)
def get_account(account_id: str) -> dict:
    store = get_store()
    account = store.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return account.model_dump()


@app.get(
    "/accounts/{account_id}/transactions",
    summary="List transactions for an account",
    tags=["Accounts"],
)
def get_account_transactions(account_id: str) -> list[dict]:
    store = get_store()
    account = store.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return [t.model_dump() for t in store.get_transactions(account.customer_id)]


# ── Alerts ─────────────────────────────────────────────────────────────────────

@app.get(
    "/alerts",
    summary="List all alerts",
    tags=["Alerts"],
)
def list_alerts(
    status: Optional[str] = Query(
        default=None,
        description="Filter by status: OPEN | INVESTIGATING | RESOLVED | ESCALATED",
    )
) -> list[dict]:
    store = get_store()
    return [a.model_dump() for a in store.get_alerts(status=status)]


@app.get(
    "/alerts/{alert_id}",
    summary="Get a single alert",
    tags=["Alerts"],
    response_model=dict,
)
def get_alert(alert_id: str) -> dict:
    store = get_store()
    alert = store.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return alert.model_dump()


# ── Cases ──────────────────────────────────────────────────────────────────────

@app.get(
    "/cases",
    summary="List all cases",
    tags=["Cases"],
)
def list_cases() -> list[dict]:
    store = get_store()
    return [c.model_dump() for c in store.get_cases()]


@app.get(
    "/cases/{case_id}",
    summary="Get a single case",
    tags=["Cases"],
    response_model=dict,
)
def get_case(case_id: str) -> dict:
    store = get_store()
    case = store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return case.model_dump()


# ── Investigation (primary FRAB integration endpoint) ─────────────────────────

@app.get(
    "/investigation/{alert_id}",
    summary="Get consolidated investigation context for an alert",
    description=(
        "Primary FRAB integration endpoint. Returns alert, customer, account, "
        "KYC, trigger transaction, transaction history, live historical statistics "
        "(trigger excluded per §27.2), beneficiaries, related transactions, and "
        "previous cases in a single response. "
        "The backend provides evidence only — FRAB makes the final decision."
    ),
    tags=["Investigation"],
    response_model=InvestigationContext,
)
def get_investigation(alert_id: str) -> InvestigationContext:
    result = build_investigation(alert_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return result


# ── Transactions — submit via GET (query-string) ───────────────────────────────
#
# The spec requires GET-only.  Transaction fields are passed as query params.
# The rule engine runs, an alert is created if a rule fires, and the result is
# returned.  This is also the endpoint the simulator calls.

@app.get(
    "/transactions/all",
    summary="List transactions (paginated)",
    description=(
        "Returns transactions from the dataset, newest first. "
        "The dataset has ~9,991 transactions, so results are PAGINATED. "
        "Use `limit` (default 100, max 1000) and `offset` to page through. "
        "Optionally filter by `customer_id`. "
        "The response includes total count and pagination metadata."
    ),
    tags=["Transactions"],
)
def list_all_transactions(
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return (1-1000)"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    customer_id: Optional[str] = Query(default=None, description="Filter by customer ID"),
) -> dict:
    store = get_store()
    all_txns = store.get_all_transactions()

    if customer_id:
        all_txns = [t for t in all_txns if t.customer_id == customer_id]

    total = len(all_txns)
    page = all_txns[offset : offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "returned": len(page),
        "transactions": [t.model_dump() for t in page],
    }

@app.get(
    "/transactions",
    summary="Submit a transaction for rule-engine evaluation",
    description=(
        "Accepts a transaction via query-string parameters, validates the "
        "customer and account, stores the transaction in the in-memory store, "
        "runs the rule engine, and creates an alert if a rule fires. "
        "Returns the transaction ID, status, and alert details if generated."
    ),
    tags=["Transactions"],
)
async def submit_transaction(
    transaction_id: Optional[str] = Query(default=None, description="Leave blank to auto-generate"),
    type: str = Query(..., description="Transaction type: TRANSFER | PAYMENT | DEBIT | CASH_OUT | CASH_IN"),
    amount: float = Query(..., description="Transaction amount (positive number)"),
    customer_id: str = Query(..., description="Customer ID, e.g. C009001507"),
    account_id: str = Query(..., description="Account ID, e.g. ACC-C009001507"),
    nameDest: str = Query(..., description="Destination account/merchant ID"),
    destination_type: str = Query(..., description="ACCOUNT or MERCHANT"),
    event_time: Optional[str] = Query(
        default=None,
        description="ISO-8601 event timestamp; defaults to now if omitted",
    ),
    is_scenario_trigger: bool = Query(default=False),
    device_id: Optional[str] = Query(default=None),
    stream_order: int = Query(default=0),
    emit_delay_ms: int = Query(default=500),
) -> dict:
    store = get_store()

    # Validate customer exists
    customer = store.get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")

    # Validate account exists
    account = store.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    # Build the transaction
    txn_id = transaction_id or f"TX{uuid.uuid4().hex[:8].upper()}"
    ts = event_time or datetime.utcnow().isoformat()

    txn = Transaction(
        transaction_id=txn_id,
        step=0,
        type=type,
        amount=amount,
        nameOrig=customer_id,
        oldbalanceOrg=0,
        newbalanceOrg=0,
        nameDest=nameDest,
        oldbalanceDest=0,
        newbalanceDest=0,
        isFraud=0,
        isFlaggedFraud=0,
        customer_id=customer_id,
        account_id=account_id,
        destination_type=destination_type,
        event_time=ts,
        is_scenario_trigger=is_scenario_trigger,
        device_id=device_id,
    )

    # Store transaction
    store.add_transaction(txn)
    logger.info("[TX] stored %s for customer %s amount=%.2f", txn_id, customer_id, amount)

    # Run rule engine
    detector = AnomalyDetector(store)
    result = detector.detect(txn)

    alert_id: Optional[str] = None
    alert_generated = False

    if result.is_anomalous:
        alert = detector.create_alert(result)
        if alert:
            # Enrich with scenario info if this is a known scenario trigger
            scenario = store.get_scenario_by_customer(customer_id)
            if scenario and txn_id == scenario.trigger_transaction_id:
                alert.scenario = scenario.scenario_type
            alert_id = alert.alert_id
            alert_generated = True
            logger.info(
                "[ALERT] %s created for tx %s customer %s severity=%s",
                alert_id, txn_id, customer_id, alert.severity.value,
            )

            # Broadcast WebSocket event
            ws_event = WebSocketEvent(
                event="NEW_ALERT",
                alert_id=alert_id,
                customer_id=customer_id,
                severity=result.severity.value,
            )
            await manager.broadcast(ws_event.model_dump())

    return {
        "transaction_id": txn_id,
        "status": "accepted",
        "alert_generated": alert_generated,
        "alert_id": alert_id,
        "risk_score": round(result.risk_score, 4),
        "severity": result.severity.value,
        "signals": [
            {"type": s.signal_type.value, "weight": s.weight, "detail": s.detail}
            for s in result.signals
        ],
    }


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    Real-time alert feed.  When GET /transactions creates an alert the server
    pushes ``{"event":"NEW_ALERT","alert_id":"ALT...","customer_id":"...","severity":"HIGH"}``.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; server is push-only
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)

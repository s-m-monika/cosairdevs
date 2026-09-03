from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Core domain models ─────────────────────────────────────────────────────────

class Customer(BaseModel):
    customer_id: str
    account_id: str
    customer_name: str
    status: str
    city: str


class Account(BaseModel):
    account_id: str
    customer_id: str
    account_type: str
    status: str
    opening_date: str
    current_balance: float


class Merchant(BaseModel):
    merchant_id: str
    status: str


class KYCProfile(BaseModel):
    customer_id: str
    kyc_status: str
    risk_category: str
    occupation: str
    annual_income_band: str
    document_type: str
    document_verified: bool
    phone_verified: bool
    address_verified: bool
    pep_status: bool


class BehaviourBaseline(BaseModel):
    customer_id: str
    transaction_count: int
    avg_transaction: float
    median_transaction: float
    max_transaction: float
    total_volume: float
    unique_beneficiaries: int
    transfer_count: int
    cashout_count: int


class Beneficiary(BaseModel):
    customer_id: str
    beneficiary_id: str
    relationship_status: str


class DestinationType(str, Enum):
    MERCHANT = "MERCHANT"
    ACCOUNT = "ACCOUNT"


class Transaction(BaseModel):
    transaction_id: str
    stream_order: int = 0
    emit_delay_ms: int = 500
    type: str
    amount: float
    customer_id: str
    account_id: str
    nameDest: str
    destination_type: str
    event_time: str
    is_scenario_trigger: bool = False
    device_id: Optional[str] = None


# ── Alert / detection models ───────────────────────────────────────────────────

class AlertSeverity(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class AlertStatus(str, Enum):
    OPEN          = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED      = "RESOLVED"
    ESCALATED     = "ESCALATED"


class Alert(BaseModel):
    alert_id: str
    transaction_id: str
    customer_id: str
    alert_type: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.OPEN
    scenario: Optional[str] = None          # e.g. "SCN10_FALSE_POSITIVE_HISTORY"
    created_at: Optional[str] = None        # ISO-8601 timestamp


class SignalType(str, Enum):
    AMOUNT_DEVIATION       = "AMOUNT_DEVIATION"
    VELOCITY_SPIKE         = "VELOCITY_SPIKE"
    NEW_DEVICE             = "NEW_DEVICE"
    NEW_BENEFICIARY        = "NEW_BENEFICIARY"
    KYC_BEHAVIOUR_MISMATCH = "KYC_BEHAVIOUR_MISMATCH"


class Signal(BaseModel):
    signal_type: SignalType
    weight: float
    detail: str


class DetectionResult(BaseModel):
    risk_score: float
    severity: AlertSeverity
    signals: list[Signal]
    transaction: Transaction
    is_anomalous: bool


# ── Device model ───────────────────────────────────────────────────────────────

class Device(BaseModel):
    device_id: str
    customer_id: str
    first_seen: str
    last_seen: str
    transaction_count: int = 0


# ── Case / scenario models ─────────────────────────────────────────────────────

class CaseRecord(BaseModel):
    case_id: str
    customer_id: str
    alert_id: str
    case_type: str
    status: str
    disposition: str
    investigation_note: str


class ScenarioRecord(BaseModel):
    scenario_id: str
    alert_id: str
    case_id: str
    customer_id: str
    scenario_type: str
    severity: str
    expected_reason: str
    trigger_transaction_id: str
    expected_action: str


# ── Historical statistics (calculated live, trigger excluded) ──────────────────

class HistoricalStatistics(BaseModel):
    historical_average: float
    historical_median: float
    historical_max: float
    historical_transaction_count: int
    historical_beneficiary_count: int
    note: str = (
        "Calculated from customer transactions excluding the trigger transaction"
    )


# ── Investigation context (primary FRAB integration response) ──────────────────

class InvestigationContext(BaseModel):
    """
    Consolidated evidence payload returned by GET /investigation/{alert_id}.
    FRAB uses this as its sole data source for investigating an alert.
    The backend supplies evidence only — FRAB makes the final decision.
    """
    alert: Optional[dict[str, Any]] = None
    customer: Optional[dict[str, Any]] = None
    account: Optional[dict[str, Any]] = None
    kyc: Optional[dict[str, Any]] = None
    trigger_transaction: Optional[dict[str, Any]] = None
    transaction_history: list[dict[str, Any]] = Field(default_factory=list)
    historical_statistics: Optional[dict[str, Any]] = None
    beneficiaries: list[dict[str, Any]] = Field(default_factory=list)
    related_transactions: list[dict[str, Any]] = Field(default_factory=list)
    previous_cases: list[dict[str, Any]] = Field(default_factory=list)


# ── WebSocket event ────────────────────────────────────────────────────────────

class WebSocketEvent(BaseModel):
    event: str
    alert_id: str
    customer_id: str
    severity: str


# ── Legacy response kept for test compatibility ────────────────────────────────

class InvestigationResponse(BaseModel):
    """
    Retained so existing tests that import InvestigationResponse continue to
    pass.  New code should use InvestigationContext.
    """
    alert: Optional[Alert] = None
    customer: Optional[Customer] = None
    kyc: Optional[KYCProfile] = None
    account: Optional[Account] = None
    recent_transactions: list[Transaction] = Field(default_factory=list)
    behaviour_profile: Optional[BehaviourBaseline] = None
    devices: list[Device] = Field(default_factory=list)
    beneficiaries: list[Beneficiary] = Field(default_factory=list)


# ── Simulator helper (unused at runtime but kept for completeness) ─────────────

class SimulatedTransaction(BaseModel):
    transaction_id: str
    type: str
    amount: float
    customer_id: str
    account_id: str
    nameDest: str
    destination_type: str
    event_time: str
    device_id: Optional[str] = None

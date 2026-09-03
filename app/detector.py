from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.config import HIGH_SEVERITY_THRESHOLD, RISK_WEIGHTS, VELOCITY_THRESHOLD, VELOCITY_WINDOW_SECONDS
from app.data_loader import DataStore, get_store
from app.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    BehaviourBaseline,
    DetectionResult,
    KYCProfile,
    Signal,
    SignalType,
    Transaction,
)
import uuid


class AnomalyDetector:
    def __init__(self, store: DataStore) -> None:
        self.store = store

    def detect(self, transaction: Transaction) -> DetectionResult:
        signals: list[Signal] = []

        amount_signal = self._check_amount_deviation(transaction)
        if amount_signal:
            signals.append(amount_signal)

        velocity_signal = self._check_velocity_spike(transaction)
        if velocity_signal:
            signals.append(velocity_signal)

        device_signal = self._check_new_device(transaction)
        if device_signal:
            signals.append(device_signal)

        beneficiary_signal = self._check_new_beneficiary(transaction)
        if beneficiary_signal:
            signals.append(beneficiary_signal)

        kyc_signal = self._check_kyc_behaviour_mismatch(transaction)
        if kyc_signal:
            signals.append(kyc_signal)

        risk_score = sum(s.weight for s in signals)
        risk_score = min(risk_score, 1.0)

        severity = (
            AlertSeverity.HIGH if risk_score >= HIGH_SEVERITY_THRESHOLD
            else AlertSeverity.MEDIUM if risk_score >= 0.40
            else AlertSeverity.LOW
        )

        return DetectionResult(
            risk_score=risk_score,
            severity=severity,
            signals=signals,
            transaction=transaction,
            is_anomalous=risk_score >= HIGH_SEVERITY_THRESHOLD,
        )

    def _check_amount_deviation(self, txn: Transaction) -> Optional[Signal]:
        behaviour = self.store.get_behaviour(txn.customer_id)
        if not behaviour or behaviour.avg_transaction == 0:
            return None
        deviation_ratio = txn.amount / behaviour.avg_transaction
        if deviation_ratio <= 5.0:
            return None

        base = RISK_WEIGHTS["AMOUNT_DEVIATION"]
        # Tiered weight: an extreme deviation is a stronger single signal.
        #   >20x  -> can alert on its own (BEHAVIOUR_DEVIATION scenarios)
        #   >10x  -> strong
        #   >5x   -> baseline
        if deviation_ratio > 10.0:
            # A >10x deviation is unambiguously anomalous (BEHAVIOUR_DEVIATION)
            # and alerts on its own.
            weight = 0.60
        elif deviation_ratio > 7.0:
            weight = 0.45
        else:
            weight = base
        return Signal(
            signal_type=SignalType.AMOUNT_DEVIATION,
            weight=weight,
            detail=f"Amount {txn.amount:.2f} is {deviation_ratio:.1f}x the avg ({behaviour.avg_transaction:.2f})",
        )

    def _check_velocity_spike(self, txn: Transaction) -> Optional[Signal]:
        customer_txs = self.store.get_transactions(txn.customer_id)
        if not customer_txs:
            return None
        try:
            txn_time = datetime.fromisoformat(txn.event_time)
        except (ValueError, TypeError):
            return None
        recent_count = 0
        for t in customer_txs:
            try:
                t_time = datetime.fromisoformat(t.event_time)
                diff = abs((txn_time - t_time).total_seconds())
                if diff <= VELOCITY_WINDOW_SECONDS and t.transaction_id != txn.transaction_id:
                    recent_count += 1
            except (ValueError, TypeError):
                continue
        if recent_count >= VELOCITY_THRESHOLD:
            weight = RISK_WEIGHTS["VELOCITY_SPIKE"]
            return Signal(
                signal_type=SignalType.VELOCITY_SPIKE,
                weight=weight,
                detail=f"{recent_count + 1} transactions within {VELOCITY_WINDOW_SECONDS}s window",
            )
        return None

    def _check_new_device(self, txn: Transaction) -> Optional[Signal]:
        if not txn.device_id:
            return None
        devices = self.store.get_devices(txn.customer_id)
        for d in devices:
            if d.device_id == txn.device_id:
                if d.transaction_count <= 1:
                    weight = RISK_WEIGHTS["NEW_DEVICE"]
                    return Signal(
                        signal_type=SignalType.NEW_DEVICE,
                        weight=weight,
                        detail=f"Device {txn.device_id} first seen for customer",
                    )
                return None
        weight = RISK_WEIGHTS["NEW_DEVICE"]
        return Signal(
            signal_type=SignalType.NEW_DEVICE,
            weight=weight,
            detail=f"Unknown device {txn.device_id} for customer",
        )

    def _check_new_beneficiary(self, txn: Transaction) -> Optional[Signal]:
        # Only ACCOUNT-to-ACCOUNT transfers involve beneficiaries.
        # Merchant payments (destination_type=MERCHANT) are not "new beneficiary" events.
        if str(txn.destination_type).upper() == "MERCHANT":
            return None

        known_beneficiaries = self.store.get_beneficiaries(txn.customer_id)
        # Map beneficiary_id -> relationship_status (ESTABLISHED / NEW)
        relationship = {b.beneficiary_id: str(b.relationship_status).upper() for b in known_beneficiaries}

        is_new = (txn.nameDest not in relationship) or (relationship.get(txn.nameDest) == "NEW")
        if not is_new:
            return None

        base = RISK_WEIGHTS["NEW_BENEFICIARY"]
        # A significant transfer to a new beneficiary is a stronger signal than a
        # small one. Scale up when the amount is large relative to the customer's
        # baseline, so a clear "new beneficiary" scenario alerts on the signal set.
        weight = base
        behaviour = self.store.get_behaviour(txn.customer_id)
        if behaviour and behaviour.avg_transaction > 0:
            ratio = txn.amount / behaviour.avg_transaction
            if ratio > 3.0:
                weight = 0.45
            elif ratio > 1.5:
                weight = 0.30

        if txn.nameDest not in relationship:
            detail = f"Destination {txn.nameDest} not in known beneficiaries"
        else:
            detail = f"Destination {txn.nameDest} is a newly-added beneficiary (relationship_status=NEW)"

        return Signal(
            signal_type=SignalType.NEW_BENEFICIARY,
            weight=weight,
            detail=detail,
        )

    def _check_kyc_behaviour_mismatch(self, txn: Transaction) -> Optional[Signal]:
        kyc = self.store.get_kyc(txn.customer_id)
        if not kyc:
            return None
        if kyc.occupation in ("STUDENT", "RETIRED") and txn.amount > 100000:
            weight = RISK_WEIGHTS["KYC_BEHAVIOUR_MISMATCH"]
            return Signal(
                signal_type=SignalType.KYC_BEHAVIOUR_MISMATCH,
                weight=weight,
                detail=f"High amount {txn.amount:.2f} for {kyc.occupation} (income band: {kyc.annual_income_band})",
            )
        if kyc.annual_income_band in ("0-3L", "3L-5L") and txn.amount > 200000:
            weight = RISK_WEIGHTS["KYC_BEHAVIOUR_MISMATCH"]
            return Signal(
                signal_type=SignalType.KYC_BEHAVIOUR_MISMATCH,
                weight=weight,
                detail=f"Amount {txn.amount:.2f} exceeds expected range for income band {kyc.annual_income_band}",
            )
        return None

    def create_alert(self, result: DetectionResult) -> Optional[Alert]:
        if not result.is_anomalous:
            return None
        alert_id = f"ALT{uuid.uuid4().hex[:8].upper()}"
        alert = Alert(
            alert_id=alert_id,
            transaction_id=result.transaction.transaction_id,
            customer_id=result.transaction.customer_id,
            alert_type="_".join(s.signal_type.value for s in result.signals),
            severity=result.severity,
            status=AlertStatus.OPEN,
        )
        self.store.add_alert(alert)
        return alert

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
        if deviation_ratio > 5.0:
            weight = RISK_WEIGHTS["AMOUNT_DEVIATION"]
            return Signal(
                signal_type=SignalType.AMOUNT_DEVIATION,
                weight=weight,
                detail=f"Amount {txn.amount:.2f} is {deviation_ratio:.1f}x the avg ({behaviour.avg_transaction:.2f})",
            )
        return None

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
        known_beneficiaries = self.store.get_beneficiaries(txn.customer_id)
        known_ids = {b.beneficiary_id for b in known_beneficiaries}
        if txn.nameDest not in known_ids:
            weight = RISK_WEIGHTS["NEW_BENEFICIARY"]
            return Signal(
                signal_type=SignalType.NEW_BENEFICIARY,
                weight=weight,
                detail=f"Destination {txn.nameDest} not in known beneficiaries",
            )
        return None

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

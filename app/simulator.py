from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.data_loader import DataStore, get_store
from app.detector import AnomalyDetector
from app.models import (
    Alert,
    BehaviourBaseline,
    DetectionResult,
    Transaction,
    WebSocketEvent,
)


class Simulator:
    def __init__(self, store: Optional[DataStore] = None) -> None:
        self.store = store or get_store()
        self.detector = AnomalyDetector(self.store)

    def simulate_normal_transaction(self, customer_id: str) -> Optional[DetectionResult]:
        customer = self.store.get_customer(customer_id)
        if not customer:
            return None

        behaviour = self.store.get_behaviour(customer_id)
        if not behaviour:
            return None

        txn = Transaction(
            transaction_id=f"TXSIM{uuid.uuid4().hex[:8].upper()}",
            step=0,
            type="TRANSFER",
            amount=round(behaviour.avg_transaction * 0.9, 2),
            nameOrig=customer_id,
            oldbalanceOrg=0,
            newbalanceOrg=0,
            nameDest=f"M{uuid.uuid4().hex[:10]}",
            oldbalanceDest=0,
            newbalanceDest=0,
            isFraud=0,
            isFlaggedFraud=0,
            customer_id=customer_id,
            account_id=customer.account_id,
            destination_type="MERCHANT",
            event_time=datetime.now().isoformat(),
            is_scenario_trigger=False,
        )

        self.store.add_transaction(txn)
        result = self.detector.detect(txn)
        return result

    def simulate_anomalous_transaction(
        self,
        customer_id: str,
        amount: Optional[float] = None,
        new_device_id: str = "DEV-NEW-001",
        new_beneficiary: str = "C999999999",
    ) -> Optional[DetectionResult]:
        customer = self.store.get_customer(customer_id)
        if not customer:
            return None

        behaviour = self.store.get_behaviour(customer_id)
        if not behaviour:
            return None

        txn_amount = amount or round(behaviour.avg_transaction * 12, 2)

        txn = Transaction(
            transaction_id=f"TXSIM{uuid.uuid4().hex[:8].upper()}",
            step=0,
            type="TRANSFER",
            amount=txn_amount,
            nameOrig=customer_id,
            oldbalanceOrg=0,
            newbalanceOrg=0,
            nameDest=new_beneficiary,
            oldbalanceDest=0,
            newbalanceDest=0,
            isFraud=0,
            isFlaggedFraud=0,
            customer_id=customer_id,
            account_id=customer.account_id,
            destination_type="ACCOUNT",
            event_time=datetime.now().isoformat(),
            is_scenario_trigger=True,
            device_id=new_device_id,
        )

        self.store.add_transaction(txn)

        devices = self.store.get_devices(customer_id)
        new_device_count = 1
        for d in devices:
            if d.device_id == new_device_id:
                break
        else:
            from app.models import Device
            dev = Device(
                device_id=new_device_id,
                customer_id=customer_id,
                first_seen=txn.event_time,
                last_seen=txn.event_time,
                transaction_count=0,
            )
            self.store.devices.setdefault(customer_id, []).append(dev)

        result = self.detector.detect(txn)
        return result

    def run_demo_scenario(
        self,
        customer_id: str = "C009001507",
    ) -> Optional[dict]:
        customer = self.store.get_customer(customer_id)
        if not customer:
            return None

        behaviour = self.store.get_behaviour(customer_id)
        if not behaviour:
            return None

        large_amount = round(behaviour.avg_transaction * 12, 2)
        new_device_id = "DEV-DEMO-001"
        new_beneficiary = "C999999999"

        result = self.simulate_anomalous_transaction(
            customer_id=customer_id,
            amount=large_amount,
            new_device_id=new_device_id,
            new_beneficiary=new_beneficiary,
        )

        if not result:
            return None

        alert = self.detector.create_alert(result)

        event = None
        if alert:
            event = WebSocketEvent(
                event="FRAUD_ALERT",
                alert_id=alert.alert_id,
                customer_id=customer_id,
                severity=alert.severity.value,
            )

        txn = result.transaction
        txn_record = {
            "transaction_id": txn.transaction_id,
            "type": txn.type,
            "amount": txn.amount,
            "customer_id": txn.customer_id,
            "account_id": txn.account_id,
            "nameDest": txn.nameDest,
            "destination_type": txn.destination_type,
            "event_time": txn.event_time,
            "device_id": txn.device_id,
        }

        return {
            "transaction": txn_record,
            "detection": {
                "risk_score": result.risk_score,
                "severity": result.severity.value,
                "is_anomalous": result.is_anomalous,
                "signals": [
                    {"type": s.signal_type.value, "weight": s.weight, "detail": s.detail}
                    for s in result.signals
                ],
            },
            "alert": alert.model_dump() if alert else None,
            "event": event.model_dump() if event else None,
        }

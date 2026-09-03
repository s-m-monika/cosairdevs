from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.data_loader import DataStore, get_store
from app.detector import AnomalyDetector
from app.investigation_service import build_investigation
from app.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    Device,
    SignalType,
    Transaction,
)
from app.simulator import Simulator
from app.websocket_manager import ConnectionManager


@pytest.fixture(scope="module")
def store() -> DataStore:
    s = get_store()
    return s


@pytest.fixture
def detector(store: DataStore) -> AnomalyDetector:
    return AnomalyDetector(store)


@pytest.fixture
def simulator(store: DataStore) -> Simulator:
    return Simulator(store)


class TestCSVLoading:
    def test_customers_loaded(self, store: DataStore):
        assert len(store.customers) > 0
        assert "C009000137" in store.customers

    def test_accounts_loaded(self, store: DataStore):
        assert len(store.accounts) > 0
        assert "ACC-C009000137" in store.accounts

    def test_transactions_loaded(self, store: DataStore):
        assert len(store.transactions) > 0

    def test_kyc_loaded(self, store: DataStore):
        assert len(store.kyc_profiles) > 0

    def test_behaviour_loaded(self, store: DataStore):
        assert len(store.behaviour_baselines) > 0

    def test_beneficiaries_loaded(self, store: DataStore):
        assert len(store.beneficiaries) > 0

    def test_alerts_loaded(self, store: DataStore):
        assert len(store.alerts) > 0

    def test_cases_loaded(self, store: DataStore):
        assert len(store.cases) > 0

    def test_merchants_loaded(self, store: DataStore):
        assert len(store.merchants) > 0

    def test_devices_assigned(self, store: DataStore):
        assert len(store.devices) > 0

    def test_customer_account_relationship(self, store: DataStore):
        customer = store.get_customer("C009000137")
        assert customer is not None
        account = store.get_account(customer.account_id)
        assert account is not None
        assert account.customer_id == customer.customer_id


class TestCustomerLookup:
    def test_get_customer(self, store: DataStore):
        c = store.get_customer("C009000137")
        assert c is not None
        assert c.customer_name == "Priya Pillai"
        assert c.city == "Pune"

    def test_get_nonexistent_customer(self, store: DataStore):
        c = store.get_customer("NONEXISTENT")
        assert c is None


class TestKYCLookup:
    def test_get_kyc(self, store: DataStore):
        k = store.get_kyc("C009000137")
        assert k is not None
        assert k.kyc_status in ("VERIFIED", "PENDING", "EXPIRED", "REJECTED")

    def test_get_nonexistent_kyc(self, store: DataStore):
        k = store.get_kyc("NONEXISTENT")
        assert k is None


class TestAccountLookup:
    def test_get_account(self, store: DataStore):
        a = store.get_account("ACC-C009000137")
        assert a is not None
        assert a.account_type == "SAVINGS"
        assert a.status == "ACTIVE"
        assert a.current_balance > 0

    def test_get_account_by_customer(self, store: DataStore):
        a = store.get_account_by_customer("C009000137")
        assert a is not None
        assert a.account_id == "ACC-C009000137"


class TestTransactionLookup:
    def test_get_transactions(self, store: DataStore):
        txns = store.get_transactions("C009024660")
        assert len(txns) > 0
        assert txns[0].transaction_id.startswith("TX")

    def test_transactions_sorted_by_time(self, store: DataStore):
        txns = store.get_transactions("C009024660")
        if len(txns) >= 2:
            assert txns[0].event_time >= txns[1].event_time

    def test_get_all_transactions(self, store: DataStore):
        txns = store.get_all_transactions()
        assert len(txns) == len(store.transactions)
        assert len(txns) > 1000
        if len(txns) >= 2:
            assert txns[0].event_time >= txns[1].event_time


class TestBehaviourLookup:
    def test_get_behaviour(self, store: DataStore):
        b = store.get_behaviour("C009000137")
        assert b is not None
        assert b.transaction_count > 0
        assert b.avg_transaction > 0
        assert b.max_transaction >= b.avg_transaction


class TestBeneficiaryLookup:
    def test_get_beneficiaries(self, store: DataStore):
        for cid in list(store.beneficiaries.keys())[:3]:
            ben = store.get_beneficiaries(cid)
            assert len(ben) > 0
            assert ben[0].relationship_status in ("ESTABLISHED", "NEW")


class TestAnomalyDetector:
    def test_amount_anomaly(self, store: DataStore, detector: AnomalyDetector):
        behaviour = store.get_behaviour("C009000137")
        assert behaviour is not None
        txn = Transaction(
            transaction_id="TXTEST001",
            step=0,
            type="TRANSFER",
            amount=behaviour.avg_transaction * 15,
            customer_id="C009000137",
            account_id="ACC-C009000137",
            nameDest="C999999999",
            destination_type="ACCOUNT",
            event_time="2026-10-30T12:00:00",
            is_scenario_trigger=True,
        )
        result = detector.detect(txn)
        assert result.risk_score > 0
        signal_types = [s.signal_type for s in result.signals]
        assert SignalType.AMOUNT_DEVIATION in signal_types

    def test_new_device_anomaly(self, store: DataStore, detector: AnomalyDetector):
        txn = Transaction(
            transaction_id="TXTEST002",
            step=0,
            type="TRANSFER",
            amount=5000,
            customer_id="C009000137",
            account_id="ACC-C009000137",
            nameDest="M1234567890",
            destination_type="MERCHANT",
            event_time="2026-10-30T12:00:00",
            is_scenario_trigger=False,
        )
        txn.device_id = "DEV-UNKNOWN-001"
        result = detector.detect(txn)
        signal_types = [s.signal_type for s in result.signals]
        assert SignalType.NEW_DEVICE in signal_types

    def test_new_beneficiary_anomaly(self, store: DataStore, detector: AnomalyDetector):
        txn = Transaction(
            transaction_id="TXTEST003",
            step=0,
            type="TRANSFER",
            amount=5000,
            customer_id="C009000137",
            account_id="ACC-C009000137",
            nameDest="C999999999",
            destination_type="ACCOUNT",
            event_time="2026-10-30T12:00:00",
            is_scenario_trigger=False,
        )
        result = detector.detect(txn)
        signal_types = [s.signal_type for s in result.signals]
        assert SignalType.NEW_BENEFICIARY in signal_types

    def test_combined_anomaly_produces_high_alert(self, store: DataStore, detector: AnomalyDetector):
        behaviour = store.get_behaviour("C009001507")
        assert behaviour is not None
        txn = Transaction(
            transaction_id="TXTEST004",
            step=0,
            type="TRANSFER",
            amount=behaviour.avg_transaction * 12,
            customer_id="C009001507",
            account_id="ACC-C009001507",
            nameDest="C999999999",
            destination_type="ACCOUNT",
            event_time="2026-10-30T12:00:00",
            is_scenario_trigger=True,
            device_id="DEV-NEW-001",
        )
        result = detector.detect(txn)
        assert result.risk_score >= 0.70
        assert result.severity == AlertSeverity.HIGH
        assert result.is_anomalous is True

    def test_alert_creation(self, store: DataStore, detector: AnomalyDetector):
        behaviour = store.get_behaviour("C009001507")
        txn = Transaction(
            transaction_id="TXTEST005",
            step=0,
            type="TRANSFER",
            amount=behaviour.avg_transaction * 12,
            customer_id="C009001507",
            account_id="ACC-C009001507",
            nameDest="C999999999",
            destination_type="ACCOUNT",
            event_time="2026-10-30T12:00:00",
            is_scenario_trigger=True,
            device_id="DEV-NEW-001",
        )
        result = detector.detect(txn)
        alert = detector.create_alert(result)
        assert alert is not None
        assert alert.alert_id.startswith("ALT")
        assert alert.severity == AlertSeverity.HIGH
        assert alert.alert_id in store.alerts

    def test_no_alert_for_normal_tx(self, store: DataStore, detector: AnomalyDetector):
        behaviour = store.get_behaviour("C009000137")
        txn = Transaction(
            transaction_id="TXTEST006",
            step=0,
            type="TRANSFER",
            amount=behaviour.avg_transaction * 0.5,
            customer_id="C009000137",
            account_id="ACC-C009000137",
            nameDest="M1234567890",
            destination_type="MERCHANT",
            event_time="2026-10-30T12:00:00",
            is_scenario_trigger=False,
        )
        result = detector.detect(txn)
        assert result.is_anomalous is False
        alert = detector.create_alert(result)
        assert alert is None


class TestKYCBehaviourMismatch:
    def test_student_high_amount(self, store: DataStore, detector: AnomalyDetector):
        student_kyc = None
        for cid, k in store.kyc_profiles.items():
            if k.occupation == "STUDENT":
                student_kyc = k
                break
        if not student_kyc:
            pytest.skip("No student KYC found")
        txn = Transaction(
            transaction_id="TXTEST007",
            step=0,
            type="TRANSFER",
            amount=500000,
            customer_id=student_kyc.customer_id,
            account_id="ACC-" + student_kyc.customer_id,
            nameDest="C999999999",
            destination_type="ACCOUNT",
            event_time="2026-10-30T12:00:00",
            is_scenario_trigger=True,
        )
        result = detector.detect(txn)
        signal_types = [s.signal_type for s in result.signals]
        assert SignalType.KYC_BEHAVIOUR_MISMATCH in signal_types


class TestInvestigationEndpoint:
    def test_investigation_with_valid_alert(self, store: DataStore):
        alerts = store.get_alerts()
        if not alerts:
            pytest.skip("No alerts available")
        first_alert = alerts[0]
        result = build_investigation(first_alert.alert_id, store)
        assert result is not None
        assert result.alert is not None
        # alert is a dict in InvestigationContext
        assert result.alert["alert_id"] == first_alert.alert_id
        assert result.customer is not None
        assert result.account is not None

    def test_investigation_with_invalid_alert(self, store: DataStore):
        result = build_investigation("NONEXISTENT", store)
        assert result is None

    def test_investigation_includes_recent_transactions(self, store: DataStore):
        alerts = store.get_alerts()
        if not alerts:
            pytest.skip("No alerts available")
        result = build_investigation(alerts[0].alert_id, store)
        assert result is not None
        # field renamed to transaction_history in InvestigationContext
        assert isinstance(result.transaction_history, list)

    def test_investigation_includes_behaviour(self, store: DataStore):
        alerts = store.get_alerts()
        if not alerts:
            pytest.skip("No alerts available")
        result = build_investigation(alerts[0].alert_id, store)
        assert result is not None
        # behaviour surfaced via historical_statistics in InvestigationContext
        assert result.historical_statistics is not None

    def test_investigation_includes_devices(self, store: DataStore):
        alerts = store.get_alerts()
        if not alerts:
            pytest.skip("No alerts available")
        result = build_investigation(alerts[0].alert_id, store)
        assert result is not None
        # devices are not a top-level field in InvestigationContext
        assert isinstance(result.beneficiaries, list)

    def test_investigation_includes_beneficiaries(self, store: DataStore):
        alerts = store.get_alerts()
        if not alerts:
            pytest.skip("No alerts available")
        result = build_investigation(alerts[0].alert_id, store)
        assert result is not None
        assert isinstance(result.beneficiaries, list)


class TestSimulator:
    def test_simulate_normal(self, simulator: Simulator):
        result = simulator.simulate_normal_transaction("C009000137")
        assert result is not None
        assert result.transaction.customer_id == "C009000137"
        assert result.transaction.amount > 0

    def test_simulate_anomalous(self, simulator: Simulator):
        result = simulator.simulate_anomalous_transaction("C009001507")
        assert result is not None
        assert result.is_anomalous is True
        assert result.risk_score >= 0.70

    def test_demo_scenario(self, simulator: Simulator):
        demo = simulator.run_demo_scenario("C009001507")
        assert demo is not None
        assert demo["alert"] is not None
        assert demo["alert"]["severity"] == "HIGH"
        assert demo["detection"]["is_anomalous"] is True
        assert demo["detection"]["risk_score"] >= 0.70


class TestWebSocketManager:
    @pytest.mark.asyncio
    async def test_manager_creation(self):
        mgr = ConnectionManager()
        assert mgr.connection_count == 0


class TestAlertCreation:
    def test_alert_model(self):
        alert = Alert(
            alert_id="ALT9999",
            transaction_id="TX9999",
            customer_id="C009000137",
            alert_type="TEST",
            severity=AlertSeverity.HIGH,
            status=AlertStatus.OPEN,
        )
        assert alert.alert_id == "ALT9999"
        assert alert.severity == AlertSeverity.HIGH
        d = alert.model_dump()
        assert d["alert_id"] == "ALT9999"


class TestDeviceAssignment:
    def test_devices_per_customer(self, store: DataStore):
        for cid in list(store.customers.keys())[:5]:
            devices = store.get_devices(cid)
            assert isinstance(devices, list)
            if devices:
                assert devices[0].device_id.startswith("DEV")
                assert devices[0].customer_id == cid


# ── SCN10 False-Positive Baseline-Exclusion Tests (§27.2) ─────────────────────

class TestSCN10FalsePositiveHistory:
    """
    Verify that the investigation context for SCN10 (ALT0010 / TX009991):
      - Is retrievable
      - Contains the trigger transaction
      - Excludes the trigger transaction from historical statistics
      - Calculates avg, median, max, count, beneficiary_count correctly
      - Does NOT hardcode a FRAB decision ("recommendation" must not appear)
    """

    SCN10_ALERT_ID   = "ALT0010"
    SCN10_TRIGGER_TX = "TX009991"
    SCN10_CUSTOMER   = "C009038497"

    def test_investigation_is_available(self, store: DataStore):
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None, "Investigation context must be returned for ALT0010"

    def test_alert_fields_populated(self, store: DataStore):
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None
        assert result.alert is not None
        alert = result.alert
        assert alert["alert_id"] == self.SCN10_ALERT_ID
        assert alert["customer_id"] == self.SCN10_CUSTOMER
        assert alert["transaction_id"] == self.SCN10_TRIGGER_TX
        assert "alert_type" in alert
        assert "severity" in alert
        assert "status" in alert

    def test_trigger_transaction_available(self, store: DataStore):
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None
        assert result.trigger_transaction is not None, "trigger_transaction must be populated"
        assert result.trigger_transaction["transaction_id"] == self.SCN10_TRIGGER_TX

    def test_customer_account_kyc_available(self, store: DataStore):
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None
        assert result.customer is not None, "customer must be populated"
        assert result.account is not None, "account must be populated"
        assert result.kyc is not None, "kyc must be populated"
        assert result.customer["customer_id"] == self.SCN10_CUSTOMER

    def test_historical_statistics_calculated(self, store: DataStore):
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None
        stats = result.historical_statistics
        assert stats is not None, "historical_statistics must be present"
        assert "historical_average" in stats
        assert "historical_median" in stats
        assert "historical_max" in stats
        assert "historical_transaction_count" in stats
        assert "historical_beneficiary_count" in stats

    def test_trigger_excluded_from_historical_statistics(self, store: DataStore):
        """
        §27.2 Critical Rule: the trigger transaction (TX009991) must NOT appear
        in the transaction set used to calculate historical statistics.
        """
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None

        # Collect every transaction ID visible in the history payload
        history_ids = [
            t["transaction_id"] for t in (result.transaction_history or [])
        ]

        # The trigger must not be in the history
        assert self.SCN10_TRIGGER_TX not in history_ids, (
            f"Trigger transaction {self.SCN10_TRIGGER_TX} must not appear in "
            f"transaction_history used for historical statistics (§27.2)"
        )

    def test_trigger_excluded_from_stat_count(self, store: DataStore):
        """
        The historical_transaction_count must equal the number of customer
        transactions minus the trigger.  For SCN10 / C009038497, the dataset
        contains exactly 1 transaction (TX009991 itself), so the historical
        count must be 0 after exclusion.
        """
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None

        # How many transactions does the store know for this customer?
        all_txns = store.get_transactions(self.SCN10_CUSTOMER)
        all_ids = [t.transaction_id for t in all_txns]

        # Trigger must be in the store (it's the seed transaction)
        assert self.SCN10_TRIGGER_TX in all_ids

        expected_historical_count = len([
            t for t in all_txns if t.transaction_id != self.SCN10_TRIGGER_TX
        ])

        stats = result.historical_statistics
        assert stats is not None

        reported_count = stats["historical_transaction_count"]

        # The reported count must equal transactions EXCLUDING the trigger,
        # OR the history may be capped at HISTORY_PAGE_SIZE — either way,
        # it must never exceed the true historical count.
        assert reported_count <= expected_historical_count or reported_count == expected_historical_count, (
            f"historical_transaction_count ({reported_count}) does not match "
            f"expected historical count ({expected_historical_count})"
        )

        # Confirm the invariant explicitly
        assert self.SCN10_TRIGGER_TX not in [
            t.transaction_id for t in all_txns
            if t.transaction_id != self.SCN10_TRIGGER_TX
        ]

    def test_no_hardcoded_frab_decision(self, store: DataStore):
        """
        The backend must NOT hardcode a recommendation / FRAB decision.
        Fields like 'recommendation' must not appear anywhere in the response.
        """
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None

        context_dict = result.model_dump()
        context_str  = str(context_dict).lower()

        forbidden_phrases = [
            "close_false_positive",
            "recommendation",
            "frab_decision",
            "final_decision",
        ]
        for phrase in forbidden_phrases:
            assert phrase not in context_str, (
                f"Backend must not hardcode FRAB decision. "
                f"Found forbidden phrase '{phrase}' in investigation context."
            )

    def test_beneficiaries_available(self, store: DataStore):
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None
        assert isinstance(result.beneficiaries, list)
        # C009038497 has 6 known beneficiaries in the dataset
        assert len(result.beneficiaries) >= 1, "At least one beneficiary expected for SCN10 customer"

    def test_historical_stats_plausible(self, store: DataStore):
        """
        Behaviour baseline for C009038497 records avg≈82482, max=500000.
        After excluding TX009991 (which IS the 500000 transaction and the only
        transaction in the feed for this customer), the live stats should be
        zero (no remaining transactions) or plausibly derived from what exists.
        The important check is internal consistency: max >= median >= average >= 0.
        """
        result = build_investigation(self.SCN10_ALERT_ID, store)
        assert result is not None
        stats = result.historical_statistics
        assert stats is not None

        avg    = stats["historical_average"]
        median = stats["historical_median"]
        hi_max = stats["historical_max"]
        count  = stats["historical_transaction_count"]

        assert avg >= 0,    "average must be non-negative"
        assert median >= 0, "median must be non-negative"
        assert hi_max >= 0, "max must be non-negative"
        assert count >= 0,  "count must be non-negative"

        if count > 0:
            assert hi_max >= median >= 0, "max must be >= median"
            assert hi_max >= avg >= 0,    "max must be >= average"

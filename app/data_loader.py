from __future__ import annotations

import os
from typing import Optional

import pandas as pd

from app.config import CSV_MAP, DATA_DIR
from app.models import (
    Account,
    Alert,
    AlertSeverity,
    AlertStatus,
    BehaviourBaseline,
    Beneficiary,
    CaseRecord,
    Customer,
    Device,
    KYCProfile,
    Merchant,
    ScenarioRecord,
    Transaction,
)


class DataStore:
    def __init__(self) -> None:
        self.customers: dict[str, Customer] = {}
        self.accounts: dict[str, Account] = {}
        self.merchants: dict[str, Merchant] = {}
        self.kyc_profiles: dict[str, KYCProfile] = {}
        self.behaviour_baselines: dict[str, BehaviourBaseline] = {}
        self.beneficiaries: dict[str, list[Beneficiary]] = {}
        self.transactions: dict[str, Transaction] = {}
        self.customer_transactions: dict[str, list[Transaction]] = {}
        self.alerts: dict[str, Alert] = {}
        self.cases: dict[str, CaseRecord] = {}
        self.scenarios: dict[str, ScenarioRecord] = {}
        self.devices: dict[str, list[Device]] = {}
        self._loaded = False

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _csv_path(self, key: str) -> str:
        filename = CSV_MAP[key]
        return os.path.join(DATA_DIR, filename)

    # ── Loaders ────────────────────────────────────────────────────────────────

    def load_all(self) -> None:
        if self._loaded:
            return
        self._load_customers()
        self._load_accounts()
        self._load_merchants()
        self._load_kyc_profiles()
        self._load_behaviour_baselines()
        self._load_beneficiaries()
        self._load_transactions()
        self._load_alerts()
        self._load_cases()
        self._load_scenarios()
        self._assign_devices()
        self._loaded = True

    def _load_customers(self) -> None:
        df = pd.read_csv(self._csv_path("customers"))
        for _, row in df.iterrows():
            c = Customer(
                customer_id=str(row["customer_id"]).strip(),
                account_id=str(row["account_id"]).strip(),
                customer_name=str(row["customer_name"]).strip(),
                status=str(row["status"]).strip(),
                city=str(row["city"]).strip(),
            )
            self.customers[c.customer_id] = c

    def _load_accounts(self) -> None:
        df = pd.read_csv(self._csv_path("accounts"))
        for _, row in df.iterrows():
            a = Account(
                account_id=str(row["account_id"]).strip(),
                customer_id=str(row["customer_id"]).strip(),
                account_type=str(row["account_type"]).strip(),
                status=str(row["status"]).strip(),
                opening_date=str(row["opening_date"]).strip(),
                current_balance=float(row["current_balance"]),
            )
            self.accounts[a.account_id] = a

    def _load_merchants(self) -> None:
        # merchants.csv actually holds KYC profiles — there is no separate
        # merchant file in this dataset.  Load as a stub so the store key exists.
        self.merchants = {}

    def _load_kyc_profiles(self) -> None:
        df = pd.read_csv(self._csv_path("kyc_profiles"))
        for _, row in df.iterrows():
            k = KYCProfile(
                customer_id=str(row["customer_id"]).strip(),
                kyc_status=str(row["kyc_status"]).strip(),
                risk_category=str(row["risk_category"]).strip(),
                occupation=str(row["occupation"]).strip(),
                annual_income_band=str(row["annual_income_band"]).strip(),
                document_type=str(row["document_type"]).strip(),
                document_verified=str(row["document_verified"]).strip().upper() == "TRUE",
                phone_verified=str(row["phone_verified"]).strip().upper() == "TRUE",
                address_verified=str(row["address_verified"]).strip().upper() == "TRUE",
                pep_status=str(row["pep_status"]).strip().upper() == "TRUE",
            )
            self.kyc_profiles[k.customer_id] = k

    def _load_behaviour_baselines(self) -> None:
        df = pd.read_csv(self._csv_path("behaviour_baseline"))
        for _, row in df.iterrows():
            b = BehaviourBaseline(
                customer_id=str(row["customer_id"]).strip(),
                transaction_count=int(row["transaction_count"]),
                avg_transaction=float(row["avg_transaction"]),
                median_transaction=float(row["median_transaction"]),
                max_transaction=float(row["max_transaction"]),
                total_volume=float(row["total_volume"]),
                unique_beneficiaries=int(row["unique_beneficiaries"]),
                transfer_count=int(row["transfer_count"]),
                cashout_count=int(row["cashout_count"]),
            )
            self.behaviour_baselines[b.customer_id] = b

    def _load_beneficiaries(self) -> None:
        df = pd.read_csv(self._csv_path("beneficiaries"))
        for _, row in df.iterrows():
            cid = str(row["customer_id"]).strip()
            ben = Beneficiary(
                customer_id=cid,
                beneficiary_id=str(row["beneficiary_id"]).strip(),
                relationship_status=str(row["relationship_status"]).strip(),
            )
            self.beneficiaries.setdefault(cid, []).append(ben)

    def _load_transactions(self) -> None:
        df = pd.read_csv(self._csv_path("transactions"))
        for _, row in df.iterrows():
            t = Transaction(
                transaction_id=str(row["transaction_id"]).strip(),
                stream_order=int(row["stream_order"]),
                emit_delay_ms=int(row["emit_delay_ms"]),
                type=str(row["type"]).strip(),
                amount=float(row["amount"]),
                customer_id=str(row["customer_id"]).strip(),
                account_id=str(row["account_id"]).strip(),
                nameDest=str(row["nameDest"]).strip(),
                destination_type=str(row["destination_type"]).strip(),
                event_time=str(row["event_time"]).strip(),
                is_scenario_trigger=(
                    str(row.get("is_scenario_trigger", "FALSE")).strip().upper() == "TRUE"
                ),
            )
            self.transactions[t.transaction_id] = t
            self.customer_transactions.setdefault(t.customer_id, []).append(t)

    def _load_alerts(self) -> None:
        df = pd.read_csv(self._csv_path("alerts"))
        for _, row in df.iterrows():
            a = Alert(
                alert_id=str(row["alert_id"]).strip(),
                transaction_id=str(row["transaction_id"]).strip(),
                customer_id=str(row["customer_id"]).strip(),
                alert_type=str(row["alert_type"]).strip(),
                severity=AlertSeverity(str(row["severity"]).strip()),
                status=AlertStatus(str(row.get("status", "OPEN")).strip()),
            )
            self.alerts[a.alert_id] = a

    def _load_cases(self) -> None:
        df = pd.read_csv(self._csv_path("cases"))
        for _, row in df.iterrows():
            c = CaseRecord(
                case_id=str(row["case_id"]).strip(),
                customer_id=str(row["customer_id"]).strip(),
                alert_id=str(row["alert_id"]).strip(),
                case_type=str(row["case_type"]).strip(),
                status=str(row["status"]).strip(),
                disposition=str(row["disposition"]).strip(),
                investigation_note=str(row["investigation_note"]).strip(),
            )
            self.cases[c.case_id] = c

    def _load_scenarios(self) -> None:
        df = pd.read_csv(self._csv_path("scenarios"))
        for _, row in df.iterrows():
            s = ScenarioRecord(
                scenario_id=str(row["scenario_id"]).strip(),
                alert_id=str(row["alert_id"]).strip(),
                case_id=str(row["case_id"]).strip(),
                customer_id=str(row["customer_id"]).strip(),
                scenario_type=str(row["scenario_type"]).strip(),
                severity=str(row["severity"]).strip(),
                expected_reason=str(row["expected_reason"]).strip(),
                trigger_transaction_id=str(row["trigger_transaction_id"]).strip(),
                expected_action=str(row["expected_action"]).strip(),
            )
            self.scenarios[s.scenario_id] = s

    def _assign_devices(self) -> None:
        """Assign one synthetic device per customer based on transaction history."""
        device_counter = 1
        for cid in sorted(self.customer_transactions):
            txs = self.customer_transactions[cid]
            if not txs:
                continue
            device_id = f"DEV{device_counter:03d}"
            device_counter += 1
            sorted_txs = sorted(txs, key=lambda t: t.event_time)
            d = Device(
                device_id=device_id,
                customer_id=cid,
                first_seen=sorted_txs[0].event_time,
                last_seen=sorted_txs[-1].event_time,
                transaction_count=len(sorted_txs),
            )
            self.devices.setdefault(cid, []).append(d)

    # ── Read accessors ─────────────────────────────────────────────────────────

    def get_customer(self, customer_id: str) -> Optional[Customer]:
        return self.customers.get(customer_id)

    def get_account(self, account_id: str) -> Optional[Account]:
        return self.accounts.get(account_id)

    def get_account_by_customer(self, customer_id: str) -> Optional[Account]:
        for a in self.accounts.values():
            if a.customer_id == customer_id:
                return a
        return None

    def get_kyc(self, customer_id: str) -> Optional[KYCProfile]:
        return self.kyc_profiles.get(customer_id)

    def get_behaviour(self, customer_id: str) -> Optional[BehaviourBaseline]:
        return self.behaviour_baselines.get(customer_id)

    def get_beneficiaries(self, customer_id: str) -> list[Beneficiary]:
        return self.beneficiaries.get(customer_id, [])

    def get_transactions(self, customer_id: str) -> list[Transaction]:
        """All transactions for a customer, newest first."""
        return sorted(
            self.customer_transactions.get(customer_id, []),
            key=lambda t: t.event_time,
            reverse=True,
        )

    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        return self.transactions.get(transaction_id)

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        return self.alerts.get(alert_id)

    def get_alerts(self, status: Optional[str] = None) -> list[Alert]:
        alerts = list(self.alerts.values())
        if status:
            alerts = [a for a in alerts if a.status.value.upper() == status.upper()]
        return alerts

    def get_devices(self, customer_id: str) -> list[Device]:
        return self.devices.get(customer_id, [])

    def get_case(self, case_id: str) -> Optional[CaseRecord]:
        return self.cases.get(case_id)

    def get_cases(self) -> list[CaseRecord]:
        return list(self.cases.values())

    def get_case_by_alert(self, alert_id: str) -> Optional[CaseRecord]:
        for c in self.cases.values():
            if c.alert_id == alert_id:
                return c
        return None

    def get_scenario_by_alert(self, alert_id: str) -> Optional[ScenarioRecord]:
        for s in self.scenarios.values():
            if s.alert_id == alert_id:
                return s
        return None

    def get_scenario_by_customer(self, customer_id: str) -> Optional[ScenarioRecord]:
        for s in self.scenarios.values():
            if s.customer_id == customer_id:
                return s
        return None

    # ── Write accessors ────────────────────────────────────────────────────────

    def add_alert(self, alert: Alert) -> None:
        self.alerts[alert.alert_id] = alert

    def add_transaction(self, txn: Transaction) -> None:
        self.transactions[txn.transaction_id] = txn
        self.customer_transactions.setdefault(txn.customer_id, []).append(txn)


# ── Module-level singleton ─────────────────────────────────────────────────────

_store: Optional[DataStore] = None


def get_store() -> DataStore:
    global _store
    if _store is None:
        _store = DataStore()
        _store.load_all()
    return _store

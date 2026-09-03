from __future__ import annotations

import statistics
from typing import Optional

from app.data_loader import DataStore, get_store
from app.models import HistoricalStatistics, InvestigationContext


# Maximum number of history transactions returned in the payload.
# Statistics are always calculated from the FULL set regardless of this cap.
HISTORY_PAGE_SIZE = 50


def build_investigation(
    alert_id: str,
    store: Optional[DataStore] = None,
) -> Optional[InvestigationContext]:
    """
    Build a consolidated investigation context for the given alert.

    Rule §27.2 — Historical statistics MUST exclude the trigger transaction.
    """
    store = store or get_store()

    # ── 1. Alert ───────────────────────────────────────────────────────────────
    alert = store.get_alert(alert_id)
    if not alert:
        return None

    trigger_tx_id = alert.transaction_id

    # ── 2. Customer ────────────────────────────────────────────────────────────
    customer = store.get_customer(alert.customer_id)

    # ── 3. Account ─────────────────────────────────────────────────────────────
    account: object = None
    if customer:
        account = store.get_account(customer.account_id)
    if not account:
        account = store.get_account_by_customer(alert.customer_id)

    # ── 4. KYC ─────────────────────────────────────────────────────────────────
    kyc = store.get_kyc(alert.customer_id)

    # ── 5. Trigger transaction ─────────────────────────────────────────────────
    trigger_txn = store.get_transaction(trigger_tx_id)

    # ── 6. All customer transactions, newest first ─────────────────────────────
    all_customer_txns = store.get_transactions(alert.customer_id)

    # Historical set = everything EXCEPT the trigger transaction
    historical_txns = [t for t in all_customer_txns if t.transaction_id != trigger_tx_id]

    # ── 7. Live historical statistics (§27.2 — trigger excluded) ──────────────
    historical_stats: Optional[HistoricalStatistics] = None
    if historical_txns:
        amounts = [t.amount for t in historical_txns]
        unique_bens = len({t.nameDest for t in historical_txns})
        historical_stats = HistoricalStatistics(
            historical_average=round(sum(amounts) / len(amounts), 2),
            historical_median=round(statistics.median(amounts), 2),
            historical_max=round(max(amounts), 2),
            historical_transaction_count=len(historical_txns),
            historical_beneficiary_count=unique_bens,
        )
    else:
        # No prior transactions — this is the customer's first known transaction.
        historical_stats = HistoricalStatistics(
            historical_average=0.0,
            historical_median=0.0,
            historical_max=0.0,
            historical_transaction_count=0,
            historical_beneficiary_count=0,
            note=(
                "No prior transactions found for this customer. "
                "Trigger transaction is the only known record."
            ),
        )

    # ── 8. Paginated history for the response payload ──────────────────────────
    # Statistics above use the FULL historical set.  The payload is capped.
    history_page = historical_txns[:HISTORY_PAGE_SIZE]

    # ── 9. Related transactions ────────────────────────────────────────────────
    # Transactions that share the same destination as the trigger transaction,
    # from ANY customer — useful for mule/burst scenario evidence.
    related: list = []
    if trigger_txn:
        dest = trigger_txn.nameDest
        for txn in store.transactions.values():
            if (
                txn.nameDest == dest
                and txn.transaction_id != trigger_tx_id
            ):
                related.append(txn)
        # Sort newest first, cap at 20
        related.sort(key=lambda t: t.event_time, reverse=True)
        related = related[:20]

    # ── 10. Previous cases for this customer ──────────────────────────────────
    previous_cases = [
        c for c in store.get_cases()
        if c.customer_id == alert.customer_id and c.alert_id != alert_id
    ]

    # ── 11. Beneficiaries ─────────────────────────────────────────────────────
    beneficiaries = store.get_beneficiaries(alert.customer_id)

    # ── 12. Enrich alert dict with scenario info if available ─────────────────
    scenario = store.get_scenario_by_alert(alert_id)
    alert_dict = alert.model_dump()
    if scenario:
        alert_dict["scenario"] = scenario.scenario_type
        alert_dict["scenario_id"] = scenario.scenario_id
        alert_dict["expected_reason"] = scenario.expected_reason
        # NOTE: expected_action is dataset metadata for context only.
        # FRAB makes the final decision — we do not emit a hardcoded recommendation.

    return InvestigationContext(
        alert=alert_dict,
        customer=customer.model_dump() if customer else None,
        account=account.model_dump() if account else None,
        kyc=kyc.model_dump() if kyc else None,
        trigger_transaction=trigger_txn.model_dump() if trigger_txn else None,
        transaction_history=[t.model_dump() for t in history_page],
        historical_statistics=historical_stats.model_dump() if historical_stats else None,
        beneficiaries=[b.model_dump() for b in beneficiaries],
        related_transactions=[t.model_dump() for t in related],
        previous_cases=[c.model_dump() for c in previous_cases],
    )

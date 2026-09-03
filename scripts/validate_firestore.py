#!/usr/bin/env python3
"""
Firestore Validation Script
============================
Dynamically checks that all expected collections are populated, document
counts are plausible, cross-collection relationships are intact, and all
10 scenarios have the data they need.

Prints PASS / FAIL for every check and exits with code 1 if any check fails.

Usage
-----
    # Requires USE_FIRESTORE=true and GOOGLE_CLOUD_PROJECT set
    USE_FIRESTORE=true GOOGLE_CLOUD_PROJECT=my-project python scripts/validate_firestore.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import GOOGLE_CLOUD_PROJECT, USE_FIRESTORE
from app.firestore_service import get_firestore_client

# ── Minimum expected document counts per collection ──────────────────────────
MIN_COUNTS: dict[str, int] = {
    "customers":          290,
    "accounts":           290,
    "transactions":        70,
    "beneficiaries":     1000,
    "kyc_profiles":       290,
    "behaviour_baseline": 290,
    "alerts":              10,
    "cases":               10,
    "scenarios":           10,
}

# ── Known scenario IDs and their expected alert / case cross-references ───────
SCENARIOS = [
    {"scenario_id": "SCN01", "alert_id": "ALT0001", "case_id": "CASE0001", "customer_id": "C009001507", "trigger_tx": "TX009955"},
    {"scenario_id": "SCN02", "alert_id": "ALT0002", "case_id": "CASE0002", "customer_id": "C009005617", "trigger_tx": "TX009963"},
    {"scenario_id": "SCN03", "alert_id": "ALT0003", "case_id": "CASE0003", "customer_id": "C009009727", "trigger_tx": "TX009967"},
    {"scenario_id": "SCN04", "alert_id": "ALT0004", "case_id": "CASE0004", "customer_id": "C009013837", "trigger_tx": "TX009968"},
    {"scenario_id": "SCN05", "alert_id": "ALT0005", "case_id": "CASE0005", "customer_id": "C009017947", "trigger_tx": "TX009969"},
    {"scenario_id": "SCN06", "alert_id": "ALT0006", "case_id": "CASE0006", "customer_id": "C009022057", "trigger_tx": "TX009970"},
    {"scenario_id": "SCN07", "alert_id": "ALT0007", "case_id": "CASE0007", "customer_id": "C009026167", "trigger_tx": "TX009971"},
    {"scenario_id": "SCN08", "alert_id": "ALT0008", "case_id": "CASE0008", "customer_id": "C009030277", "trigger_tx": "TX009981"},
    {"scenario_id": "SCN09", "alert_id": "ALT0009", "case_id": "CASE0009", "customer_id": "C009034387", "trigger_tx": "TX009982"},
    {"scenario_id": "SCN10", "alert_id": "ALT0010", "case_id": "CASE0010", "customer_id": "C009038497", "trigger_tx": "TX009991"},
]


def _pass(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _count_collection(client, name: str) -> int:
    """Return number of documents in a Firestore collection."""
    try:
        return sum(1 for _ in client.collection(name).stream())
    except Exception as e:
        print(f"         (error counting {name}: {e})")
        return -1


def _get_doc(client, collection: str, doc_id: str) -> dict | None:
    try:
        doc = client.collection(collection).document(doc_id).get()
        return doc.to_dict() if doc.exists else None
    except Exception:
        return None


def check_connection(client) -> bool:
    print("\n[CHECK] Firestore connection")
    try:
        # Simple probe — list first document of customers
        next(iter(client.collection("customers").limit(1).stream()), None)
        _pass("Connected to Firestore")
        return True
    except Exception as e:
        _fail(f"Cannot connect to Firestore: {e}")
        return False


def check_collection_counts(client) -> int:
    print("\n[CHECK] Collection document counts")
    failures = 0
    for collection, minimum in MIN_COUNTS.items():
        count = _count_collection(client, collection)
        if count < 0:
            _fail(f"{collection}: could not count documents")
            failures += 1
        elif count < minimum:
            _fail(f"{collection}: {count} documents (expected ≥ {minimum})")
            failures += 1
        else:
            _pass(f"{collection}: {count} documents (≥ {minimum})")
    return failures


def check_scenario_documents(client) -> int:
    print("\n[CHECK] Scenario documents (all 10 scenarios)")
    failures = 0
    for scn in SCENARIOS:
        sid = scn["scenario_id"]
        doc = _get_doc(client, "scenarios", sid)
        if doc is None:
            _fail(f"{sid}: not found in scenarios collection")
            failures += 1
        else:
            _pass(f"{sid}: found in scenarios collection")
    return failures


def check_alert_case_cross_refs(client) -> int:
    print("\n[CHECK] Alert ↔ case cross-references")
    failures = 0
    for scn in SCENARIOS:
        alert_id = scn["alert_id"]
        case_id  = scn["case_id"]
        cust_id  = scn["customer_id"]

        alert = _get_doc(client, "alerts", alert_id)
        if alert is None:
            _fail(f"{alert_id}: not found in alerts")
            failures += 1
        elif alert.get("customer_id") != cust_id:
            _fail(f"{alert_id}: customer_id mismatch ({alert.get('customer_id')} ≠ {cust_id})")
            failures += 1
        else:
            _pass(f"{alert_id}: customer_id matches ({cust_id})")

        case = _get_doc(client, "cases", case_id)
        if case is None:
            _fail(f"{case_id}: not found in cases")
            failures += 1
        elif case.get("alert_id") != alert_id:
            _fail(f"{case_id}: alert_id mismatch ({case.get('alert_id')} ≠ {alert_id})")
            failures += 1
        else:
            _pass(f"{case_id}: alert_id matches ({alert_id})")

    return failures


def check_trigger_transactions(client) -> int:
    print("\n[CHECK] Trigger transactions present in Firestore")
    failures = 0
    for scn in SCENARIOS:
        tx_id = scn["trigger_tx"]
        doc = _get_doc(client, "transactions", tx_id)
        if doc is None:
            _fail(f"{tx_id}: not found in transactions ({scn['scenario_id']})")
            failures += 1
        else:
            _pass(f"{tx_id}: present ({scn['scenario_id']})")
    return failures


def check_customer_kyc_account(client) -> int:
    print("\n[CHECK] Customer → KYC + account for all scenario customers")
    failures = 0
    for scn in SCENARIOS:
        cust_id = scn["customer_id"]

        cust = _get_doc(client, "customers", cust_id)
        if cust is None:
            _fail(f"{cust_id}: not found in customers")
            failures += 1
            continue
        _pass(f"{cust_id}: found in customers")

        kyc = _get_doc(client, "kyc_profiles", cust_id)
        if kyc is None:
            _fail(f"{cust_id}: KYC profile missing")
            failures += 1
        else:
            _pass(f"{cust_id}: KYC profile present")

        acc_id = cust.get("account_id")
        if not acc_id:
            _fail(f"{cust_id}: no account_id field on customer document")
            failures += 1
        else:
            acc = _get_doc(client, "accounts", acc_id)
            if acc is None:
                _fail(f"{cust_id}: account {acc_id} not found in accounts")
                failures += 1
            else:
                _pass(f"{cust_id}: account {acc_id} present")

    return failures


def check_scn10_false_positive(client) -> int:
    """
    SCN10-specific check: the behaviour_baseline for C009038497 must show
    a max_transaction ≥ 400000, proving prior high-value activity exists.
    """
    print("\n[CHECK] SCN10 false-positive evidence in behaviour_baseline")
    failures = 0
    cust_id = "C009038497"
    doc = _get_doc(client, "behaviour_baseline", cust_id)
    if doc is None:
        _fail(f"behaviour_baseline for {cust_id} not found")
        return 1

    max_tx = doc.get("max_transaction", 0)
    avg_tx = doc.get("avg_transaction", 0)
    count  = doc.get("transaction_count", 0)

    if max_tx >= 400000:
        _pass(f"SCN10: max_transaction={max_tx} (≥400000 — high-value history evident)")
    else:
        _fail(f"SCN10: max_transaction={max_tx} (expected ≥400000)")
        failures += 1

    if count >= 10:
        _pass(f"SCN10: transaction_count={count} (≥10 — historical depth available)")
    else:
        _fail(f"SCN10: transaction_count={count} (expected ≥10)")
        failures += 1

    _pass(f"SCN10: avg_transaction={avg_tx} (context for FRAB reasoning)")
    return failures


def main() -> None:
    print("=" * 60)
    print("  Synthetic Bank — Firestore Validation")
    print(f"  Project : {GOOGLE_CLOUD_PROJECT or '(not set)'}")
    print("=" * 60)

    if not USE_FIRESTORE:
        print(
            "\n[WARN] USE_FIRESTORE is not set to 'true'.\n"
            "       Set USE_FIRESTORE=true to run Firestore checks.\n"
        )
        sys.exit(0)

    if not GOOGLE_CLOUD_PROJECT:
        print("[ERROR] GOOGLE_CLOUD_PROJECT is not set.", file=sys.stderr)
        sys.exit(1)

    client = get_firestore_client()
    if client is None:
        print("[ERROR] Could not obtain Firestore client.", file=sys.stderr)
        sys.exit(1)

    total_failures = 0

    if not check_connection(client):
        sys.exit(1)

    total_failures += check_collection_counts(client)
    total_failures += check_scenario_documents(client)
    total_failures += check_alert_case_cross_refs(client)
    total_failures += check_trigger_transactions(client)
    total_failures += check_customer_kyc_account(client)
    total_failures += check_scn10_false_positive(client)

    print("\n" + "=" * 60)
    if total_failures == 0:
        print("  [PASS] All Firestore validation checks passed.")
    else:
        print(f"  [FAIL] {total_failures} check(s) failed. See output above.")
    print("=" * 60 + "\n")

    sys.exit(0 if total_failures == 0 else 1)


if __name__ == "__main__":
    main()

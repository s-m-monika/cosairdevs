#!/usr/bin/env python3
"""
Synthetic Bank — Transaction Simulator
=======================================
Reads data/seed/transactions.csv (the simulator feed) and replays transactions
through the backend HTTP API via GET /transactions.

The simulator NEVER writes directly to Firestore.  All data flows through the
API so the full pipeline (validate → store → rule-engine → alert → WebSocket)
is exercised exactly as it would be in production.

Usage
-----
# Run a single scenario:
python scripts/run_simulator.py --base-url http://localhost:8000 --scenario SCN01 --delay 2

# Run all scenarios:
python scripts/run_simulator.py --base-url http://localhost:8000 --all --delay 2

# Replay every row in the feed (no scenario filter):
python scripts/run_simulator.py --base-url http://localhost:8000 --delay 0.5

Scenario → trigger-transaction mapping
---------------------------------------
The simulator_feed.csv contains the full ordered transaction stream (72 rows).
Each scenario has a trigger transaction (is_scenario_trigger=TRUE) plus
supporting context transactions that belong to the same scenario window.

Scenario IDs (scenario_type column of kyc_profiles.csv / scenarios table):
  SCN01  HIGH_VALUE_NEW_BENEFICIARY   TX009955
  SCN02  VELOCITY_SPIKE               TX009963
  SCN03  STRUCTURING_PATTERN          TX009967
  SCN04  BEHAVIOUR_DEVIATION          TX009968
  SCN05  NEW_BENEFICIARY              TX009969
  SCN06  KYC_MISMATCH                 TX009970
  SCN07  MULE_PATTERN                 TX009971
  SCN08  REPEATED_CASHOUT             TX009981
  SCN09  CROSS_ACCOUNT_BURST          TX009982
  SCN10  FALSE_POSITIVE_HISTORY       TX009991
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import urllib.parse
import urllib.request
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "seed"
FEED_FILE = DATA_DIR / "transactions.csv"
SCENARIOS_FILE = DATA_DIR / "kyc_profiles.csv"   # actually the scenarios table

# Map SCN label → trigger transaction ID (from kyc_profiles.csv / scenarios)
# Built dynamically at startup from the CSV; this dict is a fallback.
_SCENARIO_TRIGGER_FALLBACK: dict[str, str] = {
    "SCN01": "TX009955",
    "SCN02": "TX009963",
    "SCN03": "TX009967",
    "SCN04": "TX009968",
    "SCN05": "TX009969",
    "SCN06": "TX009970",
    "SCN07": "TX009971",
    "SCN08": "TX009981",
    "SCN09": "TX009982",
    "SCN10": "TX009991",
}

# Map SCN label → customer_id (needed to select supporting context transactions)
_SCENARIO_CUSTOMER_FALLBACK: dict[str, str] = {
    "SCN01": "C009001507",
    "SCN02": "C009005617",
    "SCN03": "C009009727",
    "SCN04": "C009013837",
    "SCN05": "C009017947",
    "SCN06": "C009022057",
    "SCN07": "C009026167",
    "SCN08": "C009030277",
    "SCN09": "C009034387",
    "SCN10": "C009038497",
}


def _load_scenarios() -> tuple[dict[str, str], dict[str, str]]:
    """Return (scenario_id → trigger_tx_id, scenario_id → customer_id)."""
    trigger_map: dict[str, str] = dict(_SCENARIO_TRIGGER_FALLBACK)
    customer_map: dict[str, str] = dict(_SCENARIO_CUSTOMER_FALLBACK)
    if not SCENARIOS_FILE.exists():
        return trigger_map, customer_map
    with open(SCENARIOS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scn = row.get("scenario_id", "").strip()
            if scn:
                trigger_map[scn] = row.get("trigger_transaction_id", "").strip()
                customer_map[scn] = row.get("customer_id", "").strip()
    return trigger_map, customer_map


def _load_feed() -> list[dict]:
    """Load all rows from simulator_feed.csv sorted by stream_order."""
    rows: list[dict] = []
    with open(FEED_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k.strip(): v.strip() for k, v in row.items()})
    rows.sort(key=lambda r: int(r.get("stream_order", 0)))
    return rows


def _select_rows(
    rows: list[dict],
    scenario_id: str | None,
    trigger_map: dict[str, str],
    customer_map: dict[str, str],
) -> list[dict]:
    """
    Return the subset of feed rows relevant to the requested scenario.

    Strategy:
    - The trigger transaction (is_scenario_trigger=TRUE) for the scenario.
    - All supporting context transactions whose customer_id matches the
      scenario's known customer OR whose destination matches the scenario
      customers (catches mule/burst patterns where multiple customers funnel
      to one destination).
    """
    if scenario_id is None:
        return rows  # run everything

    scn = scenario_id.upper()
    trigger_tx = trigger_map.get(scn)
    primary_customer = customer_map.get(scn)

    if not trigger_tx:
        print(f"[WARN] Unknown scenario {scn}. Running full feed.")
        return rows

    # Mule / burst scenarios involve multiple customers; collect all
    # customers that appear in non-trigger rows associated with this scenario
    # by finding the trigger row's nameDest and including rows going there.
    trigger_dest: str | None = None
    for r in rows:
        if r["transaction_id"] == trigger_tx:
            trigger_dest = r.get("nameDest")
            break

    selected: list[dict] = []
    for r in rows:
        cid = r.get("customer_id", "")
        dest = r.get("nameDest", "")
        tx_id = r.get("transaction_id", "")
        is_trigger = r.get("is_scenario_trigger", "FALSE").upper() == "TRUE"

        if tx_id == trigger_tx:
            selected.append(r)
        elif cid == primary_customer:
            selected.append(r)
        elif trigger_dest and dest == trigger_dest and not is_trigger:
            # Supporting context row (another customer sending to the same dest)
            selected.append(r)

    # Keep stream_order sort
    selected.sort(key=lambda r: int(r.get("stream_order", 0)))
    return selected


def _build_url(base_url: str, row: dict) -> str:
    """Construct the GET /transactions URL from a feed row."""
    base = base_url.rstrip("/")
    params = {
        "transaction_id": row["transaction_id"],
        "type": row["type"],
        "amount": row["amount"],
        "customer_id": row["customer_id"],
        "account_id": row["account_id"],
        "nameDest": row["nameDest"],
        "destination_type": row["destination_type"],
        "event_time": row["event_time"],
        "is_scenario_trigger": row.get("is_scenario_trigger", "false").lower(),
        "stream_order": row.get("stream_order", "0"),
        "emit_delay_ms": row.get("emit_delay_ms", "500"),
    }
    return f"{base}/transactions?{urllib.parse.urlencode(params)}"


def _call(url: str) -> tuple[int, dict]:
    """HTTP GET and return (status_code, response_body_dict)."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body}
        return e.code, data
    except Exception as exc:
        return 0, {"error": str(exc)}


def _print_result(row: dict, status: int, resp: dict) -> None:
    tx_id = row["transaction_id"]
    amount = row["amount"]
    customer = row["customer_id"]
    is_trigger = row.get("is_scenario_trigger", "FALSE").upper() == "TRUE"
    marker = "★ TRIGGER" if is_trigger else "  context"

    if status in (200, 201):
        alert_id = resp.get("alert_id")
        alert_flag = resp.get("alert_generated", False)
        severity = resp.get("severity", "")
        if alert_flag and alert_id:
            print(
                f"  [PASS] {marker} {tx_id} | {customer} | {amount}"
                f" → ALERT {alert_id} [{severity}]"
            )
        else:
            print(f"  [PASS] {marker} {tx_id} | {customer} | {amount} → accepted (no alert)")
    else:
        print(f"  [FAIL] {marker} {tx_id} | {customer} | {amount} → HTTP {status}: {resp}")


def run(
    base_url: str,
    scenario_id: str | None,
    delay: float,
    dry_run: bool,
) -> None:
    trigger_map, customer_map = _load_scenarios()
    all_rows = _load_feed()
    rows = _select_rows(all_rows, scenario_id, trigger_map, customer_map)

    label = scenario_id or "ALL"
    print(f"\n{'='*60}")
    print(f"  Synthetic Bank Simulator — scenario: {label}")
    print(f"  Base URL  : {base_url}")
    print(f"  Rows      : {len(rows)}")
    print(f"  Delay     : {delay}s between requests")
    print(f"  Dry run   : {dry_run}")
    print(f"{'='*60}\n")

    passed = failed = alerts = 0

    for i, row in enumerate(rows):
        url = _build_url(base_url, row)

        if dry_run:
            print(f"  [DRY-RUN] {row['transaction_id']} → {url}")
            continue

        status, resp = _call(url)
        _print_result(row, status, resp)

        if status in (200, 201):
            passed += 1
            if resp.get("alert_generated"):
                alerts += 1
        else:
            failed += 1

        if delay > 0 and i < len(rows) - 1:
            time.sleep(delay)

    print(f"\n{'─'*60}")
    print(f"  Results for {label}:")
    print(f"    Transactions sent : {passed + failed}")
    print(f"    PASS              : {passed}")
    print(f"    FAIL              : {failed}")
    print(f"    Alerts generated  : {alerts}")
    print(f"{'─'*60}\n")

    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthetic Bank Transaction Simulator — sends transactions via GET /transactions"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--scenario",
        metavar="SCN01..SCN10",
        help="Run a specific scenario (e.g. SCN10).  Mutually exclusive with --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all scenarios (full feed).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to wait between requests (default: 1.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print URLs without sending requests.",
    )

    args = parser.parse_args()

    if args.scenario and args.all:
        parser.error("--scenario and --all are mutually exclusive")

    if not FEED_FILE.exists():
        print(f"[ERROR] Feed file not found: {FEED_FILE}", file=sys.stderr)
        sys.exit(1)

    scenario_id: str | None = None
    if args.scenario:
        scenario_id = args.scenario.upper()
    elif not args.all:
        # Default: run full feed if neither flag is given
        scenario_id = None

    run(
        base_url=args.base_url,
        scenario_id=scenario_id,
        delay=args.delay,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

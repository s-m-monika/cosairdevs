#!/usr/bin/env python3
"""
Firestore Seeder
================
Loads all data from the finalized CSV dataset into Firestore.
Safe to re-run — all writes use merge=True (idempotent upserts).

Collections seeded
------------------
  customers           document ID = customer_id
  accounts            document ID = account_id
  kyc_profiles        document ID = customer_id
  behaviour_baseline  document ID = customer_id
  beneficiaries       document ID = {customer_id}_{beneficiary_id}
  transactions        document ID = transaction_id
  alerts              document ID = alert_id
  cases               document ID = case_id
  scenarios           document ID = scenario_id

Usage
-----
    USE_FIRESTORE=true GOOGLE_CLOUD_PROJECT=my-project python scripts/seed_firestore.py

    # Seed only specific collections:
    USE_FIRESTORE=true GOOGLE_CLOUD_PROJECT=my-project \
        python scripts/seed_firestore.py --collections customers accounts alerts

    # Preview document counts without writing:
    python scripts/seed_firestore.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.data_loader import get_store
from app.firestore_service import batch_upsert, get_firestore_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# All supported collection names in seeding order
ALL_COLLECTIONS = [
    "customers",
    "accounts",
    "kyc_profiles",
    "behaviour_baseline",
    "beneficiaries",
    "transactions",
    "alerts",
    "cases",
    "scenarios",
]


def _build_documents(store, collection_name: str) -> dict[str, dict]:
    """Return {doc_id: data_dict} for the requested collection."""
    documents: dict[str, dict] = {}

    if collection_name == "customers":
        for cid, c in store.customers.items():
            documents[cid] = c.model_dump()

    elif collection_name == "accounts":
        for aid, a in store.accounts.items():
            documents[aid] = a.model_dump()

    elif collection_name == "kyc_profiles":
        for cid, k in store.kyc_profiles.items():
            documents[cid] = k.model_dump()

    elif collection_name == "behaviour_baseline":
        for cid, b in store.behaviour_baselines.items():
            documents[cid] = b.model_dump()

    elif collection_name == "beneficiaries":
        for cid, ben_list in store.beneficiaries.items():
            for b in ben_list:
                doc_id = f"{b.customer_id}_{b.beneficiary_id}"
                documents[doc_id] = b.model_dump()

    elif collection_name == "transactions":
        for tid, t in store.transactions.items():
            documents[tid] = t.model_dump()

    elif collection_name == "alerts":
        for aid, a in store.alerts.items():
            documents[aid] = a.model_dump()

    elif collection_name == "cases":
        for cid, c in store.cases.items():
            documents[cid] = c.model_dump()

    elif collection_name == "scenarios":
        for sid, s in store.scenarios.items():
            documents[sid] = s.model_dump()

    return documents


def seed_collection(store, collection_name: str, dry_run: bool = False) -> int:
    docs = _build_documents(store, collection_name)
    count = len(docs)

    if dry_run:
        logger.info("[DRY-RUN] %s: %d documents (no write)", collection_name, count)
        return count

    if count == 0:
        logger.info("%-20s  0 documents — skipping", collection_name)
        return 0

    written = batch_upsert(collection_name, docs)
    logger.info("%-20s  %d / %d documents seeded", collection_name, written, count)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Firestore from finalized CSV dataset")
    parser.add_argument(
        "--collections",
        nargs="*",
        metavar="COLLECTION",
        help=f"Collections to seed (default: all). Choices: {', '.join(ALL_COLLECTIONS)}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load CSVs and print counts but do not write to Firestore",
    )
    args = parser.parse_args()

    # Validate requested collections
    requested = args.collections or ALL_COLLECTIONS
    unknown = [c for c in requested if c not in ALL_COLLECTIONS]
    if unknown:
        logger.error("Unknown collection(s): %s. Valid: %s", unknown, ALL_COLLECTIONS)
        sys.exit(1)

    logger.info("Loading data store from CSVs…")
    store = get_store()
    logger.info(
        "Loaded: %d customers, %d accounts, %d transactions, %d alerts, %d cases, %d scenarios",
        len(store.customers),
        len(store.accounts),
        len(store.transactions),
        len(store.alerts),
        len(store.cases),
        len(store.scenarios),
    )

    if not args.dry_run:
        client = get_firestore_client()
        if client is None:
            logger.error(
                "Firestore client unavailable. "
                "Set USE_FIRESTORE=true and GOOGLE_CLOUD_PROJECT=<project-id>."
            )
            sys.exit(1)

    total = 0
    for name in requested:
        total += seed_collection(store, name, dry_run=args.dry_run)

    action = "would seed" if args.dry_run else "seeded"
    logger.info("Total documents %s: %d", action, total)


if __name__ == "__main__":
    main()

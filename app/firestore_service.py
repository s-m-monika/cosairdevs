from __future__ import annotations

import json
import logging
from typing import Any, Optional

from google.cloud import firestore

from app.config import GCP_PROJECT, USE_FIRESTORE

logger = logging.getLogger(__name__)

_client: Optional[firestore.Client] = None


def get_firestore_client() -> Optional[firestore.Client]:
    global _client
    if not USE_FIRESTORE:
        return None
    if _client is None:
        try:
            _client = firestore.Client(project=GCP_PROJECT)
            logger.info("Firestore client initialized for project %s", GCP_PROJECT)
        except Exception as e:
            logger.warning("Firestore client init failed: %s", e)
            return None
    return _client


def _collection(name: str) -> Optional[firestore.CollectionReference]:
    client = get_firestore_client()
    if client is None:
        return None
    return client.collection(name)


def upsert_document(collection_name: str, doc_id: str, data: dict[str, Any]) -> bool:
    coll = _collection(collection_name)
    if coll is None:
        return False
    try:
        coll.document(doc_id).set(data, merge=True)
        return True
    except Exception as e:
        logger.warning("Firestore upsert failed: %s/%s: %s", collection_name, doc_id, e)
        return False


def get_document(collection_name: str, doc_id: str) -> Optional[dict[str, Any]]:
    coll = _collection(collection_name)
    if coll is None:
        return None
    try:
        doc = coll.document(doc_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.warning("Firestore get failed: %s/%s: %s", collection_name, doc_id, e)
        return None


def query_collection(
    collection_name: str,
    field: str,
    op: str,
    value: Any,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    coll = _collection(collection_name)
    if coll is None:
        return []
    try:
        q = coll.where(field, op, value)
        if limit:
            q = q.limit(limit)
        return [doc.to_dict() for doc in q.stream()]
    except Exception as e:
        logger.warning("Firestore query failed: %s.%s %s %s: %s", collection_name, field, op, value, e)
        return []


def batch_upsert(collection_name: str, documents: dict[str, dict[str, Any]]) -> int:
    client = get_firestore_client()
    if client is None:
        return 0
    count = 0
    batch = client.batch()
    batch_size = 0
    for doc_id, data in documents.items():
        coll = client.collection(collection_name)
        batch.set(coll.document(doc_id), data, merge=True)
        batch_size += 1
        if batch_size >= 500:
            try:
                batch.commit()
                count += batch_size
            except Exception as e:
                logger.warning("Firestore batch commit failed: %s", e)
            batch = client.batch()
            batch_size = 0
    if batch_size > 0:
        try:
            batch.commit()
            count += batch_size
        except Exception as e:
            logger.warning("Firestore batch commit failed: %s", e)
    return count

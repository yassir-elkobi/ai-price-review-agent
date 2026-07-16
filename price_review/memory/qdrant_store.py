"""Decision-history RAG, backed by Qdrant Cloud or an in-memory fallback."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from price_review.config import get_settings
from price_review.memory.embeddings import DIMENSIONS, embed

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_client: Any = None
_ready_collection: str | None = None


def _build_client():
    from qdrant_client import QdrantClient

    settings = get_settings()
    if settings.has_qdrant_cloud:
        api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
        logger.info("Connecting to Qdrant Cloud at %s", settings.qdrant_url)
        return QdrantClient(url=settings.qdrant_url, api_key=api_key)

    logger.info("QDRANT_URL not set - using in-memory Qdrant for decision history.")
    return QdrantClient(":memory:")


def _get_client():
    global _client
    with _lock:
        if _client is None:
            _client = _build_client()
        return _client


def _ensure_collection(client, collection: str) -> None:
    global _ready_collection
    if _ready_collection == collection:
        return

    from qdrant_client.http import models as qmodels

    existing = {item.name for item in client.get_collections().collections}
    if collection not in existing:
        client.create_collection(
            collection_name=collection,
            vectors_config=qmodels.VectorParams(size=DIMENSIONS, distance=qmodels.Distance.COSINE),
        )
    _ready_collection = collection


def reset_memory_client() -> None:
    """Drop the cached client/collection state (used by tests and mode switches)."""
    global _client, _ready_collection
    with _lock:
        _client = None
        _ready_collection = None


def record_decision(
    instrument_id: str,
    decision: str,
    rule_ref: int | None = None,
    reasoning: str = "",
) -> None:
    """Persist one rendered decision so future reviews can recall it (best-effort)."""
    from qdrant_client.http import models as qmodels

    try:
        settings = get_settings()
        client = _get_client()
        _ensure_collection(client, settings.qdrant_collection)

        text = f"{instrument_id} {decision} rule {rule_ref or '?'} {reasoning}".strip()
        point = qmodels.PointStruct(
            id=str(uuid.uuid4()),
            vector=embed(text),
            payload={
                "instrument_id": instrument_id.strip().upper(),
                "decision": decision.strip().upper(),
                "rule_ref": rule_ref,
                "reasoning": reasoning,
                "timestamp": time.time(),
            },
        )
        client.upsert(collection_name=settings.qdrant_collection, points=[point])
    except Exception as exc:  # noqa: BLE001 - persistence must never break a review
        logger.warning("Failed to record decision history for %s: %s", instrument_id, exc)


def get_decision_history(instrument_id: str, limit: int = 5) -> list[dict[str, Any]]:
    from qdrant_client.http import models as qmodels

    try:
        settings = get_settings()
        client = _get_client()
        _ensure_collection(client, settings.qdrant_collection)

        upper = instrument_id.strip().upper()
        result = client.query_points(
            collection_name=settings.qdrant_collection,
            query=embed(f"{upper} decision history"),
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="instrument_id", match=qmodels.MatchValue(value=upper)
                    )
                ]
            ),
            limit=limit,
        )
        records = [point.payload for point in result.points if point.payload]
        records.sort(key=lambda record: record.get("timestamp", 0), reverse=True)
        return records
    except Exception as exc:  # noqa: BLE001 - degrade to "no history" on any backend issue
        logger.warning("Failed to fetch decision history for %s: %s", instrument_id, exc)
        return []


def get_decision_history_text(instrument_id: str, limit: int = 5) -> str:
    records = get_decision_history(instrument_id, limit=limit)
    if not records:
        return f"No prior decision history on record for {instrument_id}."

    lines = [f"Decision history for {instrument_id} (most recent first, from Qdrant):"]
    for record in records:
        timestamp = record.get("timestamp")
        when = (
            time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
            if timestamp
            else "unknown time"
        )
        rule_ref = record.get("rule_ref") or "?"
        reasoning = record.get("reasoning") or ""
        suffix = f": {reasoning}" if reasoning else ""
        lines.append(f"- [{when}] {record.get('decision', '?')} (rule {rule_ref}){suffix}")
    return "\n".join(lines)

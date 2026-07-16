"""GraphRAG over instrument/sector/event relations, via Neo4j or a local fixture."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from price_review import paths
from price_review.config import get_settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_driver: Any = None
_fixture_cache: dict[str, Any] | None = None


def _load_fixture() -> dict[str, Any]:
    global _fixture_cache
    if _fixture_cache is not None:
        return _fixture_cache
    try:
        _fixture_cache = json.loads(paths.SECTOR_GRAPH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load sector graph from %s: %s", paths.SECTOR_GRAPH_PATH, exc)
        _fixture_cache = {"instruments": {}, "correlations": {}, "sector_events": {}}
    return _fixture_cache


def reset_graph_cache() -> None:
    """Drop cached driver/fixture state (used by tests)."""
    global _driver, _fixture_cache
    with _lock:
        _driver = None
        _fixture_cache = None


def _get_driver():
    global _driver
    from neo4j import GraphDatabase

    settings = get_settings()
    with _lock:
        if _driver is None:
            password = (
                settings.neo4j_password.get_secret_value() if settings.neo4j_password else None
            )
            _driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, password))
            logger.info("Connected to Neo4j Aura at %s", settings.neo4j_uri)
        return _driver


_CYPHER_SECTOR_CONTEXT = """
MATCH (i:Instrument {id: $instrument_id})-[:BELONGS_TO]->(s:Sector)
OPTIONAL MATCH (s)<-[:AFFECTED_BY]-(e:Event)
OPTIONAL MATCH (i)-[:CORRELATED_WITH]->(peer:Instrument)
RETURN s.name AS sector, s.country AS country,
       collect(DISTINCT e.headline) AS events,
       collect(DISTINCT peer.id) AS peers
"""


def _query_neo4j(instrument_id: str) -> dict[str, Any] | None:
    driver = _get_driver()
    with driver.session() as session:
        record = session.run(_CYPHER_SECTOR_CONTEXT, instrument_id=instrument_id).single()
    if record is None:
        return None
    return {
        "sector": record["sector"],
        "country": record["country"],
        "events": [item for item in record["events"] if item],
        "peers": [item for item in record["peers"] if item],
    }


def _query_fixture(instrument_id: str) -> dict[str, Any] | None:
    fixture = _load_fixture()
    info = fixture.get("instruments", {}).get(instrument_id)
    if info is None:
        return None
    sector = info.get("sector")
    events = [
        event["headline"]
        for event in fixture.get("sector_events", {}).get(sector, [])
        if event.get("headline")
    ]
    peers = fixture.get("correlations", {}).get(instrument_id, [])
    return {"sector": sector, "country": info.get("country"), "events": events, "peers": peers}


def get_sector_context(instrument_id: str) -> dict[str, Any] | None:
    instrument_id = instrument_id.strip().upper()
    settings = get_settings()

    if settings.has_neo4j:
        try:
            result = _query_neo4j(instrument_id)
            if result is not None:
                return result
            logger.info("No Neo4j node for %s - falling back to local sector graph.", instrument_id)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully to the local fixture
            logger.warning("Neo4j query failed for %s: %s", instrument_id, exc)

    return _query_fixture(instrument_id)


def get_sector_context_text(instrument_id: str) -> str:
    context = get_sector_context(instrument_id)
    if context is None:
        return f"No sector/graph context on record for {instrument_id}."

    lines = [f"Sector context for {instrument_id}: {context['sector']} ({context['country']})."]
    if context["events"]:
        lines.append("Recent sector events:")
        lines.extend(f"- {headline}" for headline in context["events"])
    else:
        lines.append("No recent sector-wide events on record.")

    if context["peers"]:
        lines.append(f"Correlated instruments: {', '.join(context['peers'])}.")

    return "\n".join(lines)

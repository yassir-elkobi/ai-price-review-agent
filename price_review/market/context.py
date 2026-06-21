from __future__ import annotations

import json
import logging
import time
from typing import Any

from price_review import paths

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, str]] = {}
_CACHE_TTL_SECONDS = 900


def clear_market_context_cache() -> None:
    _cache.clear()


def _load_desk_events(instrument_id: str) -> list[dict[str, Any]]:
    try:
        ctx = json.loads(paths.DESK_CONTEXT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load desk context from %s: %s", paths.DESK_CONTEXT_PATH, exc)
        return []
    return list(ctx.get(instrument_id.upper(), []))


def _format_event_line(event: dict[str, Any]) -> str:
    return f"- [{event['date']}] ({event['impact']} impact) {event['headline']}"


def get_market_context_text(instrument_id: str) -> str:
    instrument_id = instrument_id.strip()
    upper = instrument_id.upper()

    cached = _cache.get(upper)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    desk_events = _load_desk_events(upper)
    if not desk_events:
        text = f"No market events on record for {instrument_id} (desk demo fixtures)."
    else:
        lines = [f"Market events for {instrument_id} (desk demo fixtures):"]
        lines.extend(_format_event_line(event) for event in desk_events)
        text = "\n".join(lines)

    _cache[upper] = (time.monotonic(), text)
    return text

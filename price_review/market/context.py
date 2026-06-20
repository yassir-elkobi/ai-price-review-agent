from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from datetime import date, timedelta
from typing import Any
from price_review import paths
from price_review.config import Settings, get_settings

logger = logging.getLogger(__name__)

OPTIONAL_FINNHUB_BASE = "https://finnhub.io/api/v1"
OPTIONAL_FINNHUB_MAX_HEADLINES = 5
OPTIONAL_FINNHUB_LOOKBACK_DAYS = 7

_cache: dict[str, tuple[float, str]] = {}


def clear_market_context_cache() -> None:
    _cache.clear()


def _optional_finnhub_eligible(instrument_id: str) -> bool:
    upper = instrument_id.upper()
    if upper == "EURUSD":
        return True
    return upper.endswith(".OQ") or upper.endswith(".L")


def _to_optional_finnhub_symbol(instrument_id: str) -> str:
    upper = instrument_id.upper()
    if upper.endswith(".OQ"):
        return upper.removesuffix(".OQ")
    return upper


def _load_desk_events(instrument_id: str) -> list[dict[str, Any]]:
    try:
        ctx = json.loads(paths.DESK_CONTEXT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load desk context from %s: %s", paths.DESK_CONTEXT_PATH, exc)
        return []
    return list(ctx.get(instrument_id.upper(), []))


def _format_event_line(event: dict[str, Any]) -> str:
    return f"- [{event['date']}] ({event['impact']} impact) {event['headline']}"


def _format_desk_only(instrument_id: str, desk_events: list[dict[str, Any]]) -> str:
    if not desk_events:
        return f"No market events on record for {instrument_id} (desk demo fixtures)."
    lines = [f"Market events for {instrument_id} (desk demo fixtures):"]
    lines.extend(_format_event_line(event) for event in desk_events)
    return "\n".join(lines)


def _format_with_optional_finnhub(
        instrument_id: str,
        desk_events: list[dict[str, Any]],
        live_events: list[dict[str, Any]],
) -> str:
    if not desk_events and not live_events:
        return f"No market events on record for {instrument_id}."

    lines = [f"Market events for {instrument_id}:"]
    lines.extend(["", "Desk notes (demo fixtures):"])
    if desk_events:
        lines.extend(_format_event_line(event) for event in desk_events)
    else:
        lines.append("- (no desk events on record)")

    if live_events:
        lines.extend([
            "",
            f"Optional Finnhub headlines (last {OPTIONAL_FINNHUB_LOOKBACK_DAYS} days):",
        ])
        lines.extend(_format_event_line(event) for event in live_events)
    return "\n".join(lines)


def _http_get_json(url: str, timeout: float = 10.0) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "ai-price-review-agent/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _optional_finnhub_news_to_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in items[:OPTIONAL_FINNHUB_MAX_HEADLINES]:
        headline = str(item.get("headline", "")).strip()
        if not headline:
            continue
        ts = item.get("datetime", 0)
        event_date = date.fromtimestamp(ts).isoformat() if ts else date.today().isoformat()
        events.append(
            {
                "date": event_date,
                "headline": headline,
                "impact": "medium",
                "type": item.get("category") or "news",
            }
        )
    return events


def _fetch_optional_finnhub_company_news(symbol: str, api_key: str) -> list[dict[str, Any]]:
    to_day = date.today()
    from_day = to_day - timedelta(days=OPTIONAL_FINNHUB_LOOKBACK_DAYS)
    params = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "from": from_day.isoformat(),
            "to": to_day.isoformat(),
            "token": api_key,
        }
    )
    data = _http_get_json(f"{OPTIONAL_FINNHUB_BASE}/company-news?{params}")
    if not isinstance(data, list):
        return []
    return _optional_finnhub_news_to_events(data)


def _fetch_optional_finnhub_forex_news(api_key: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"category": "forex", "token": api_key})
    data = _http_get_json(f"{OPTIONAL_FINNHUB_BASE}/news?{params}")
    if not isinstance(data, list):
        return []
    keywords = ("eur", "usd", "ecb", "fed", "fx", "forex", "dollar", "euro")
    filtered = [
        item
        for item in data
        if any(keyword in str(item.get("headline", "")).lower() for keyword in keywords)
    ]
    return _optional_finnhub_news_to_events(filtered or data)


def _fetch_optional_finnhub_events(instrument_id: str, api_key: str) -> list[dict[str, Any]]:
    upper = instrument_id.upper()
    if upper == "EURUSD":
        return _fetch_optional_finnhub_forex_news(api_key)
    return _fetch_optional_finnhub_company_news(_to_optional_finnhub_symbol(instrument_id), api_key)


def get_market_context_text(
        instrument_id: str,
        settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    instrument_id = instrument_id.strip()
    upper = instrument_id.upper()
    ttl = settings.market_context_cache_ttl_seconds

    cached = _cache.get(upper)
    if cached and (time.monotonic() - cached[0]) < ttl:
        return cached[1]

    def store(text: str) -> str:
        _cache[upper] = (time.monotonic(), text)
        return text

    desk_events = _load_desk_events(upper)

    if not settings.optional_finnhub_enabled:
        return store(_format_desk_only(instrument_id, desk_events))

    if not _optional_finnhub_eligible(instrument_id):
        return store(_format_desk_only(instrument_id, desk_events))

    api_key = settings.optional_finnhub_api_key.get_secret_value().strip()  # type: ignore[union-attr]
    live_events: list[dict[str, Any]] = []
    try:
        live_events = _fetch_optional_finnhub_events(instrument_id, api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Optional Finnhub fetch failed for %s: %s", instrument_id, exc)
    except Exception:
        logger.exception("Unexpected optional Finnhub error for %s", instrument_id)

    if live_events:
        return store(_format_with_optional_finnhub(instrument_id, desk_events, live_events))
    return store(_format_desk_only(instrument_id, desk_events))

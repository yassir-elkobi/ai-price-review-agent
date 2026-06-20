from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

from price_review.config import Settings, get_settings

logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"
MAX_HEADLINES = 5
NEWS_LOOKBACK_DAYS = 7

_cache: dict[str, tuple[float, str]] = {}


def clear_market_context_cache() -> None:
    _cache.clear()


def _finnhub_eligible(instrument_id: str) -> bool:
    upper = instrument_id.upper()
    if upper == "EURUSD":
        return True
    return upper.endswith(".OQ") or upper.endswith(".L")


def _to_finnhub_symbol(instrument_id: str) -> str:
    upper = instrument_id.upper()
    if upper.endswith(".OQ"):
        return upper.removesuffix(".OQ")
    return upper


def _format_event_line(event: dict[str, Any]) -> str:
    return f"- [{event['date']}] ({event['impact']} impact) {event['headline']}"


def _format_events(instrument_id: str, events: list[dict[str, Any]]) -> str:
    if not events:
        return f"No market events on record for {instrument_id}."
    lines = [f"Market events for {instrument_id} (Finnhub, last {NEWS_LOOKBACK_DAYS} days):"]
    lines.extend(_format_event_line(event) for event in events)
    return "\n".join(lines)


def _http_get_json(url: str, timeout: float = 10.0) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "ai-price-review-agent/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _finnhub_news_to_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in items[:MAX_HEADLINES]:
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


def _fetch_finnhub_company_news(symbol: str, api_key: str) -> list[dict[str, Any]]:
    to_day = date.today()
    from_day = to_day - timedelta(days=NEWS_LOOKBACK_DAYS)
    params = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "from": from_day.isoformat(),
            "to": to_day.isoformat(),
            "token": api_key,
        }
    )
    data = _http_get_json(f"{FINNHUB_BASE}/company-news?{params}")
    if not isinstance(data, list):
        return []
    return _finnhub_news_to_events(data)


def _fetch_finnhub_forex_news(api_key: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"category": "forex", "token": api_key})
    data = _http_get_json(f"{FINNHUB_BASE}/news?{params}")
    if not isinstance(data, list):
        return []
    keywords = ("eur", "usd", "ecb", "fed", "fx", "forex", "dollar", "euro")
    filtered = [
        item
        for item in data
        if any(keyword in str(item.get("headline", "")).lower() for keyword in keywords)
    ]
    return _finnhub_news_to_events(filtered or data)


def _fetch_finnhub_events(instrument_id: str, api_key: str) -> list[dict[str, Any]]:
    upper = instrument_id.upper()
    if upper == "EURUSD":
        return _fetch_finnhub_forex_news(api_key)
    return _fetch_finnhub_company_news(_to_finnhub_symbol(instrument_id), api_key)


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

    if not _finnhub_eligible(instrument_id):
        return store(_format_events(instrument_id, []))

    api_key = (
        settings.finnhub_api_key.get_secret_value().strip()
        if settings.finnhub_api_key
        else ""
    )
    if not api_key:
        return store(_format_events(instrument_id, []))

    try:
        events = _fetch_finnhub_events(instrument_id, api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Finnhub fetch failed for %s: %s", instrument_id, exc)
        events = []
    except Exception:
        logger.exception("Unexpected Finnhub error for %s", instrument_id)
        events = []

    return store(_format_events(instrument_id, events))

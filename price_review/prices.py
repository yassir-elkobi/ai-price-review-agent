"""Single source of truth for reading data/prices.json."""

import json
import logging

from price_review import paths

logger = logging.getLogger(__name__)


def load_prices() -> dict:
    try:
        return json.loads(paths.PRICES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load prices from %s: %s", paths.PRICES_PATH, exc)
        raise


def load_instrument_ids() -> set[str]:
    return {item["instrument_id"] for item in load_prices()["instruments"]}


def load_asset_class_map() -> dict[str, str]:
    return {item["instrument_id"]: item["asset_class"] for item in load_prices()["instruments"]}


def group_instruments_by_asset_class() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for item in load_prices()["instruments"]:
        groups.setdefault(item["asset_class"], []).append(item["instrument_id"])
    return groups

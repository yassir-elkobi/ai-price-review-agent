import json
import logging

from price_review import paths
from price_review.scenarios.models import ScenarioCatalog

logger = logging.getLogger(__name__)


def load_scenarios() -> ScenarioCatalog:
    try:
        raw = paths.SCENARIOS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read scenarios from %s: %s", paths.SCENARIOS_PATH, exc)
        raise
    return ScenarioCatalog.model_validate(json.loads(raw))


def load_instrument_ids() -> set[str]:
    try:
        raw = paths.PRICES_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read prices from %s: %s", paths.PRICES_PATH, exc)
        raise
    data = json.loads(raw)
    return {item["instrument_id"] for item in data["instruments"]}


def validate_scenario_references(catalog: ScenarioCatalog | None = None) -> list[str]:
    catalog = catalog or load_scenarios()
    known = load_instrument_ids()
    errors: list[str] = []
    seen_ids: set[str] = set()

    for scenario in catalog.scenarios:
        if scenario.id in seen_ids:
            errors.append(f"duplicate scenario id: {scenario.id}")
        seen_ids.add(scenario.id)

        for instrument_id in scenario.instrument_ids:
            if instrument_id not in known:
                errors.append(f"{scenario.id}: unknown instrument_id {instrument_id}")

        for outcome in scenario.expected_outcomes:
            if outcome.instrument_id not in known:
                errors.append(f"{scenario.id}: unknown outcome instrument {outcome.instrument_id}")

    return errors

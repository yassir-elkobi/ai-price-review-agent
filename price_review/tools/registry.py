import json
import logging
import threading

from langchain_core.tools import tool
from price_review import paths
from price_review.market.context import get_market_context_text

logger = logging.getLogger(__name__)

_MAX_ID_LEN = 64
_escalations_lock = threading.Lock()
ESCALATIONS: list[dict] = []


def _validate_instrument_id(instrument_id: str) -> str:
    value = instrument_id.strip()
    if not value:
        raise ValueError("instrument_id must not be empty.")
    if len(value) > _MAX_ID_LEN:
        raise ValueError(f"instrument_id is too long (max {_MAX_ID_LEN} chars).")
    return value


def _load_prices() -> dict:
    try:
        return json.loads(paths.PRICES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load prices from %s: %s", paths.PRICES_PATH, exc)
        raise


def get_escalations_snapshot() -> list[dict]:
    with _escalations_lock:
        return list(ESCALATIONS)


@tool
def list_instruments_for_validation() -> str:
    """List every instrument that needs an end-of-day price review today.

    Call this when the user asks to review all prices, the full book, or EOD prices
    without naming a specific instrument. Returns the as-of date and, for each line,
    the instrument id, name, asset class, and daily percentage change.
    """
    data = _load_prices()
    lines = [f"As-of date: {data['as_of_date']}", "Instruments to validate:"]
    for item in data["instruments"]:
        lines.append(
            f"- {item['instrument_id']} | {item['name']} | {item['asset_class']} "
            f"| change {item['pct_change']:+.2f}%"
        )
    return "\n".join(lines)


@tool
def get_price_data(instrument_id: str) -> str:
    """Return full price data for one instrument.

    Use the exact identifier (e.g. 'AAPL.OQ', 'XS1234567890', 'EURUSD').
    Returns today's price, prior price, reference price, daily change %,
    divergence vs reference %, last update, business days since refresh, and source.
    Call once per instrument before applying the rules.
    """
    try:
        instrument_id = _validate_instrument_id(instrument_id)
    except ValueError as exc:
        return str(exc)

    data = _load_prices()
    for item in data["instruments"]:
        if item["instrument_id"].upper() == instrument_id.upper():
            return json.dumps(item, ensure_ascii=False, indent=2)
    return f"No instrument found for identifier '{instrument_id}'."


@tool
def get_validation_rules() -> str:
    """Return the desk price review rules in effect today.

    Always call this first on every request. Rules are read fresh from the desk note;
    do not rely on rules from a previous turn or from memory. The text may change
    between sessions.
    """
    try:
        return paths.RULES_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read rules from %s: %s", paths.RULES_PATH, exc)
        return f"Could not read rules: {exc}"


@tool
def get_market_context(instrument_id: str) -> str:
    """Return market events that may explain a price move for the instrument.

    Call when the daily change is large, near a rule threshold, or the decision
    depends on whether an event (earnings, central bank, credit, etc.) justifies
    the move. Returns recorded events or a message that none are on file.
    """
    try:
        instrument_id = _validate_instrument_id(instrument_id)
    except ValueError as exc:
        return str(exc)
    return get_market_context_text(instrument_id)


@tool
def escalate_to_human(instrument_id: str, reason: str) -> str:
    """Escalate a case to a human reviewer instead of deciding alone.

    Use when rules conflict, the case is sensitive, data is insufficient, or the
    outcome is ambiguous. Provide the instrument id and a short, precise reason.
    The agent recommends; a human makes the final call.
    """
    try:
        instrument_id = _validate_instrument_id(instrument_id)
    except ValueError as exc:
        return str(exc)

    record = {"instrument_id": instrument_id, "reason": reason}
    with _escalations_lock:
        ESCALATIONS.append(record)
    logger.info("Escalation recorded for %s: %s", instrument_id, reason)
    return f"Case escalated to a human validator for {instrument_id}. Reason recorded: {reason}"


TOOLS = [
    list_instruments_for_validation,
    get_price_data,
    get_validation_rules,
    get_market_context,
    escalate_to_human,
]

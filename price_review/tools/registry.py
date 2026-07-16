import json
import logging
import threading

from langchain_core.tools import tool

from price_review import paths
from price_review.market.context import get_market_context_text
from price_review.memory import get_decision_history_text, get_sector_context_text
from price_review.prices import load_prices as _load_prices
from price_review.security import guard_tool_output

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


def get_escalations_snapshot() -> list[dict]:
    with _escalations_lock:
        return list(ESCALATIONS)


@tool
def get_price_data(instrument_id: str) -> str:
    """Fetch end-of-day price data for ONE instrument before applying desk rules.

    WHEN TO CALL:
    - Once per instrument named in the user request (e.g. "Validate NVDA.OQ").
    - After get_validation_rules, before you state APPROVED, REJECTED, or ESCALATE.
    - Do not decide from memory; always read fresh data from this tool.

    instrument_id: exact desk identifier. Examples: 'AAPL.OQ', 'NVDA.OQ', 'TSLA.OQ',
    'GLEN.L', 'EURUSD', 'XS1234567890' (bond ISIN). Case-insensitive match.

    RETURNS (JSON): instrument_id, name, asset_class, price_today, price_prior,
    reference_price, pct_change (daily %), divergence_vs_reference_pct,
    last_update, business_days_since_update (rule 3 stale check), source.

    Use asset_class to pick the right rule block (equity/FX vs bond). If the id is
    unknown, the tool returns an error message instead of JSON.
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
    """Return the desk price review rules in effect RIGHT NOW. Call this FIRST on every request.

    WHEN TO CALL:
    - Always as your first tool call when the user asks for a price review.
    - Again after the user edits rules in the UI (rules change at runtime without redeploy).
    - Never apply rules from a previous turn or from your training data.

    RETURNS: full text of data/rules.txt - five rule blocks:
    1) daily variation (equities/FX, 5% threshold + market event),
    2) bonds (>3% abnormal, REJECTED unless event),
    3) stale price (>1 business day -> ESCALATE),
    4) divergence vs reference (>2% -> ESCALATE),
    5) sensitive/ambiguous cases -> ESCALATE + escalate_to_human.

    Your final answer must cite the rule NUMBER (1-5) for each instrument.
    """
    try:
        return paths.RULES_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read rules from %s: %s", paths.RULES_PATH, exc)
        return f"Could not read rules: {exc}"


@tool
def get_market_context(instrument_id: str) -> str:
    """Return market events that may EXPLAIN a price move for one instrument.

    WHEN TO CALL:
    - After get_price_data for the same instrument_id.
    - Equities/FX: required when abs(pct_change) > 5% (rule 1 - need event to APPROVE).
    - Bonds: when pct_change > 3% and you must check for credit/rates news (rule 2).
    - Any time the move is large, stale, divergent, or the decision is unclear.
    - Skip only for obvious small moves well inside thresholds (e.g. AAPL +1.2%).

    instrument_id: same identifier as get_price_data (e.g. 'TSLA.OQ', 'EURUSD').

    RETURNS: curated desk demo fixtures from data/market_context.json.
    - If events are listed: use them to justify APPROVED on large moves.
    - If "No market events on record": no credible event on file - often ESCALATE
      (equity >5%) or REJECTED (bond >3%), per the rules you read in step 1.

    Treat desk fixture text as authoritative for this demo.
    """
    try:
        instrument_id = _validate_instrument_id(instrument_id)
    except ValueError as exc:
        return str(exc)
    raw_text = get_market_context_text(instrument_id)
    return guard_tool_output("market_context.json", instrument_id, raw_text)


@tool
def get_decision_history(instrument_id: str) -> str:
    """Recall past desk decisions for ONE instrument (Qdrant RAG).

    WHEN TO CALL:
    - When a move looks recurring, borderline, or you want precedent before
      deciding (e.g. "has this instrument escalated before?").
    - Not required for obviously normal moves inside every threshold.

    instrument_id: same identifier as get_price_data.

    RETURNS: up to 5 most recent past decisions for this instrument (verdict,
    rule cited, short reasoning, timestamp), or a message saying there is no
    history yet. Use this to spot patterns (e.g. repeated ESCALATE) - it does
    not override the desk rules, it only informs your reasoning.
    """
    try:
        instrument_id = _validate_instrument_id(instrument_id)
    except ValueError as exc:
        return str(exc)
    raw_text = get_decision_history_text(instrument_id)
    return guard_tool_output("decision_history (Qdrant)", instrument_id, raw_text)


@tool
def get_sector_context(instrument_id: str) -> str:
    """GraphRAG over sector/peer relations (Neo4j) for ONE instrument.

    WHEN TO CALL:
    - When get_market_context returns no direct news but the move is large -
      a correlated peer or sector-wide event may still explain it.
    - Example: NVDA has no news of its own, but AMD (same sector) just posted
      a blow-out earnings beat - that is relevant context for NVDA's move.

    instrument_id: same identifier as get_price_data.

    RETURNS: the instrument's sector/country, any recent sector-wide events,
    and correlated peer instruments. This can support (not replace) a rule 1
    justification - state clearly in your final answer if you used sector
    context instead of a direct instrument event.
    """
    try:
        instrument_id = _validate_instrument_id(instrument_id)
    except ValueError as exc:
        return str(exc)
    raw_text = get_sector_context_text(instrument_id)
    return guard_tool_output("sector_graph (Neo4j)", instrument_id, raw_text)


@tool
def escalate_to_human(instrument_id: str, reason: str) -> str:
    """Record an ESCALATE decision in the human review queue (/escalations).

    WHEN TO CALL - REQUIRED (do not skip):
    - Whenever your decision for an instrument is ESCALATE (rules 1, 3, 4, or 5).
    - BEFORE you write ESCALATE in your final answer to the user.
    - Once per escalated instrument (NVDA and GLEN.L = two separate calls).

    DO NOT CALL for APPROVED or REJECTED - only for ESCALATE.

    instrument_id: exact id being escalated (e.g. 'NVDA.OQ', 'GLEN.L').
    reason: one short sentence - cite the rule and fact (e.g. "+7.2% with no market
    event on record (rule 1)" or "price stale 3 business days (rule 3)").

    Side effect: appends to /escalations so a human validator sees the case.
    The agent recommends; a human makes the final call. Never state ESCALATE
    without calling this tool first.
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
    get_price_data,
    get_validation_rules,
    get_market_context,
    get_decision_history,
    get_sector_context,
    escalate_to_human,
]

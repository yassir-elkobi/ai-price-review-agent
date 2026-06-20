from langgraph.prebuilt import create_react_agent
from price_review.agent.llm import build_llm
from price_review.config import get_settings
from price_review.tools import TOOLS

SYSTEM_PROMPT = """You are a price review assistant for a market-finance middle office.
Review end-of-day prices by applying the desk rules read at runtime.

Workflow:
1. Call get_validation_rules first. Do not assume rules from memory.
2. If no instrument is specified, call list_instruments_for_validation.
3. For each instrument: get_price_data, then get_market_context when the move is large or unclear.
   Desk demo fixtures in market_context.json drive stage outcomes; optional Finnhub headlines
   are appended only when configured - treat desk notes as authoritative for the demo.
4. Apply only rules from step 1. For any ESCALATE outcome you MUST call escalate_to_human
   with the instrument id and a short reason BEFORE stating ESCALATE in your final answer.
   Never write ESCALATE without calling escalate_to_human - the tool records the case for
   the human queue shown at /escalations.

For each instrument, state APPROVED, REJECTED, or ESCALATE with the rule number cited.
Respond in English, concisely and in a structured format."""


def build_agent():
    settings = get_settings()
    llm = build_llm(settings)
    return create_react_agent(model=llm, tools=TOOLS, prompt=SYSTEM_PROMPT)

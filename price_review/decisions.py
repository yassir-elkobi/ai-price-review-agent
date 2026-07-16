"""Extracts per-instrument verdicts from the agent's free-text final answer.

Used by the memory layer (persist decisions) and the evaluation harness (score decisions).
"""

from __future__ import annotations

import re

from pydantic import BaseModel

_DECISION_RE = re.compile(r"\b(APPROVED|REJECTED|ESCALATE)\b", re.IGNORECASE)
_RULE_RE = re.compile(r"rule\s*#?\s*(\d)", re.IGNORECASE)
_WINDOW_BEFORE = 15
_WINDOW_AFTER = 220


class ParsedDecision(BaseModel):
    """One parsed instrument verdict extracted from the agent's free text."""

    instrument_id: str
    decision: str
    rule_ref: int | None = None


def parse_decisions(text: str, known_instrument_ids: list[str]) -> list[ParsedDecision]:
    if not text:
        return []

    upper_text = text.upper()
    results: list[ParsedDecision] = []

    for instrument_id in known_instrument_ids:
        index = upper_text.find(instrument_id.upper())
        if index == -1:
            continue

        # Look forward first so a previous instrument's decision is never picked up.
        end = index + len(instrument_id)
        forward = text[end : end + _WINDOW_AFTER]
        decision_match = _DECISION_RE.search(forward)
        rule_match = _RULE_RE.search(forward)

        if decision_match is None:
            backward = text[max(0, index - _WINDOW_BEFORE) : index]
            decision_match = _DECISION_RE.search(backward)
            rule_match = rule_match or _RULE_RE.search(backward)

        if decision_match is None:
            continue

        results.append(
            ParsedDecision(
                instrument_id=instrument_id,
                decision=decision_match.group(1).upper(),
                rule_ref=int(rule_match.group(1)) if rule_match else None,
            )
        )

    return results

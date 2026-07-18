"""Extracts per-instrument verdicts from the agent's free-text final answer.

Used by the memory layer (persist decisions) and the evaluation harness (score decisions).
"""

from __future__ import annotations

import re

from pydantic import BaseModel

_DECISION_RE = re.compile(r"\b(APPROVED|REJECTED|ESCALATE)\b", re.IGNORECASE)
_RULE_RE = re.compile(r"rule\s*#?\s*(\d)", re.IGNORECASE)
_WINDOW_BEFORE = 15
_RULE_PROXIMITY = 60


class ParsedDecision(BaseModel):
    """One parsed instrument verdict extracted from the agent's free text."""

    instrument_id: str
    decision: str
    rule_ref: int | None = None


def parse_decisions(text: str, known_instrument_ids: list[str]) -> list[ParsedDecision]:
    if not text:
        return []

    upper_text = text.upper()
    upper_ids = [instrument_id.upper() for instrument_id in known_instrument_ids]
    results: list[ParsedDecision] = []

    for instrument_id, upper_id in zip(known_instrument_ids, upper_ids):
        index = upper_text.find(upper_id)
        if index == -1:
            continue

        end = index + len(instrument_id)

        boundary = len(text)
        for other_id in upper_ids:
            if other_id == upper_id:
                continue
            pos = upper_text.find(other_id, end)
            if pos != -1:
                boundary = min(boundary, pos)

        forward = text[end:boundary]
        decision_match = _DECISION_RE.search(forward)
        rule_match = None

        if decision_match is None:
            backward = text[max(0, index - _WINDOW_BEFORE) : index]
            decision_match = _DECISION_RE.search(backward)
            rule_match = _RULE_RE.search(backward)

        if decision_match is None:
            continue

        if rule_match is None:
            near_decision = forward[
                max(0, decision_match.start() - 10) : decision_match.end() + _RULE_PROXIMITY
            ]
            rule_match = _RULE_RE.search(near_decision) or _RULE_RE.search(forward)

        results.append(
            ParsedDecision(
                instrument_id=instrument_id,
                decision=decision_match.group(1).upper(),
                rule_ref=int(rule_match.group(1)) if rule_match else None,
            )
        )

    return results

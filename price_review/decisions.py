"""Extracts per-instrument verdicts from the agent's free-text final answer.

Used by the memory layer (persist decisions) and the evaluation harness (score decisions).
"""

from __future__ import annotations

import re

from pydantic import BaseModel

_DECISION_RE = re.compile(r"\b(APPROVED|REJECTED|ESCALATE)\b", re.IGNORECASE)
_RULE_RE = re.compile(r"rule\s*#?\s*(\d)", re.IGNORECASE)

_ANCHORED_DECISION_WITH_RULE_RE = re.compile(
    r"decision\s*:?\s*[^a-zA-Z]{0,10}(APPROVED|REJECTED|ESCALATE)\b"
    r"[^\n]{0,40}?rule\s*#?\s*(\d)",
    re.IGNORECASE,
)
_ANCHORED_DECISION_RE = re.compile(
    r"decision\s*:?\s*[^a-zA-Z]{0,10}(APPROVED|REJECTED|ESCALATE)\b", re.IGNORECASE
)

_WINDOW_BEFORE = 15
_RULE_PROXIMITY = 150


class ParsedDecision(BaseModel):
    """One parsed instrument verdict extracted from the agent's free text."""

    instrument_id: str
    decision: str
    rule_ref: int | None = None


def _closest_rule_match(text: str, anchor_start: int, anchor_end: int) -> re.Match | None:
    """Return the rule mention nearest to the decision keyword, in either direction."""
    anchor = (anchor_start + anchor_end) / 2
    window_start = max(0, anchor_start - _RULE_PROXIMITY)
    window_end = anchor_end + _RULE_PROXIMITY
    candidates = list(_RULE_RE.finditer(text, window_start, window_end))
    if not candidates:
        return None
    return min(candidates, key=lambda m: abs((m.start() + m.end()) / 2 - anchor))


def _parse_window(forward: str, backward: str) -> tuple[str, int | None] | None:
    """Extract one (decision, rule) pair from a forward window and its backward fallback."""
    combined = _ANCHORED_DECISION_WITH_RULE_RE.search(forward)
    if combined is not None:
        return combined.group(1).upper(), int(combined.group(2))

    decision_match = _ANCHORED_DECISION_RE.search(forward) or _DECISION_RE.search(forward)
    rule_match = None

    if decision_match is None:
        decision_match = _ANCHORED_DECISION_RE.search(backward) or _DECISION_RE.search(backward)
        rule_match = _RULE_RE.search(backward)

    if decision_match is None:
        return None

    if rule_match is None:
        rule_match = _closest_rule_match(
            forward, decision_match.start(), decision_match.end()
        ) or _RULE_RE.search(forward)

    return decision_match.group(1).upper(), int(rule_match.group(1)) if rule_match else None


def parse_decisions(text: str, known_instrument_ids: list[str]) -> list[ParsedDecision]:
    if not text:
        return []

    upper_text = text.upper()
    upper_ids = [instrument_id.upper() for instrument_id in known_instrument_ids]
    results: list[ParsedDecision] = []

    for instrument_id, upper_id in zip(known_instrument_ids, upper_ids):
        index = upper_text.find(upper_id)

        if index == -1:
            if len(known_instrument_ids) != 1:
                continue
            parsed = _parse_window(forward=text, backward="")
            if parsed is not None:
                decision, rule_ref = parsed
                results.append(
                    ParsedDecision(
                        instrument_id=instrument_id, decision=decision, rule_ref=rule_ref
                    )
                )
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
        backward = text[max(0, index - _WINDOW_BEFORE) : index]

        parsed = _parse_window(forward=forward, backward=backward)
        if parsed is None:
            continue

        decision, rule_ref = parsed
        results.append(
            ParsedDecision(instrument_id=instrument_id, decision=decision, rule_ref=rule_ref)
        )

    return results

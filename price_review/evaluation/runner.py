"""Evaluation harness: replay data/scenarios.json against a live agent and score it.

Checks decision correctness (parsed verdict + rule vs. `expected_outcomes`) and
completeness (was `escalate_to_human` actually called for every ESCALATE?), then
aggregates the score globally, by rule number, and by asset class.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from price_review.api.trace import extract_trace
from price_review.decisions import parse_decisions
from price_review.evaluation.models import EvaluationReport, ScenarioResult
from price_review.prices import load_asset_class_map
from price_review.scenarios.loader import load_scenarios
from price_review.scenarios.models import Scenario

logger = logging.getLogger(__name__)


def _escalated_instrument_ids(steps: list[dict]) -> set[str]:
    escalated = set()
    for step in steps:
        if step.get("kind") == "call" and step.get("tool") == "escalate_to_human":
            instrument_id = (step.get("args") or {}).get("instrument_id")
            if instrument_id:
                escalated.add(str(instrument_id).strip().upper())
    return escalated


def run_scenario(agent, scenario: Scenario) -> ScenarioResult:
    result = agent.invoke({"messages": [{"role": "user", "content": scenario.query}]})
    final_answer, steps = extract_trace(result["messages"])

    known_ids = [
        outcome.instrument_id for outcome in scenario.expected_outcomes
    ] or scenario.instrument_ids
    parsed = parse_decisions(final_answer, known_ids)
    actual_by_id = {item.instrument_id.upper(): item for item in parsed}
    escalated_ids = _escalated_instrument_ids(steps)

    decision_correct = True
    completeness_ok = True
    notes: list[str] = []

    for expected in scenario.expected_outcomes:
        actual = actual_by_id.get(expected.instrument_id.upper())
        if actual is None:
            decision_correct = False
            notes.append(f"{expected.instrument_id}: no decision parsed from final answer")
        elif actual.decision != expected.decision:
            decision_correct = False
            notes.append(
                f"{expected.instrument_id}: expected {expected.decision}, got {actual.decision}"
            )
        elif actual.rule_ref is not None and actual.rule_ref != expected.rule_ref:
            decision_correct = False
            expected_rule, actual_rule = expected.rule_ref, actual.rule_ref
            notes.append(
                f"{expected.instrument_id}: rule {expected_rule} expected, got {actual_rule}"
            )

        if expected.decision == "ESCALATE" and expected.instrument_id.upper() not in escalated_ids:
            completeness_ok = False
            notes.append(
                f"{expected.instrument_id}: ESCALATE stated but escalate_to_human not called"
            )

    status = (
        "pass"
        if decision_correct and completeness_ok
        else ("amber" if decision_correct else "fail")
    )

    return ScenarioResult(
        id=scenario.id,
        title=scenario.title,
        difficulty=scenario.difficulty,
        status=status,
        decision_correct=decision_correct,
        completeness_ok=completeness_ok,
        final_answer=final_answer,
        expected=[outcome.model_dump() for outcome in scenario.expected_outcomes],
        actual=[item.model_dump() for item in parsed],
        notes="; ".join(notes),
    )


def run_all_scenarios(agent) -> EvaluationReport:
    catalog = load_scenarios()
    asset_class_map = load_asset_class_map()

    results: list[ScenarioResult] = []
    rule_totals: dict[int, int] = defaultdict(int)
    rule_passed: dict[int, int] = defaultdict(int)
    class_totals: dict[str, int] = defaultdict(int)
    class_passed: dict[str, int] = defaultdict(int)

    for scenario in catalog.scenarios:
        try:
            scenario_result = run_scenario(agent, scenario)
        except Exception as exc:  # noqa: BLE001 - one bad scenario must not kill the whole run
            logger.exception("Evaluation scenario %s failed to run", scenario.id)
            scenario_result = ScenarioResult(
                id=scenario.id,
                title=scenario.title,
                difficulty=scenario.difficulty,
                status="fail",
                decision_correct=False,
                completeness_ok=False,
                final_answer="",
                expected=[outcome.model_dump() for outcome in scenario.expected_outcomes],
                actual=[],
                notes=f"Scenario crashed: {exc}",
            )
        results.append(scenario_result)

        for expected in scenario.expected_outcomes:
            rule_totals[expected.rule_ref] += 1
            asset_class = asset_class_map.get(expected.instrument_id, "Unknown")
            class_totals[asset_class] += 1
            if scenario_result.status == "pass":
                rule_passed[expected.rule_ref] += 1
                class_passed[asset_class] += 1

    total = len(results)
    passed = sum(1 for item in results if item.status == "pass")

    return EvaluationReport(
        total=total,
        passed=passed,
        failed=total - passed,
        score=round(passed / total, 3) if total else 0.0,
        score_by_rule={
            f"rule_{rule}": round(rule_passed[rule] / count, 3)
            for rule, count in rule_totals.items()
        },
        score_by_asset_class={
            asset_class: round(class_passed[asset_class] / count, 3)
            for asset_class, count in class_totals.items()
        },
        results=results,
    )

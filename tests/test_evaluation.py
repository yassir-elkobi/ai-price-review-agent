from unittest.mock import MagicMock

from price_review.evaluation.runner import run_all_scenarios, run_scenario
from price_review.scenarios.loader import load_scenarios

EXPECTED = {
    "AAPL.OQ": ("APPROVED", 1),
    "EURUSD": ("APPROVED", 1),
    "TSLA.OQ": ("APPROVED", 1),
    "XS1234567890": ("ESCALATE", 5),
    "GLEN.L": ("ESCALATE", 3),
    "NVDA.OQ": ("ESCALATE", 1),
}


def _make_ai_message(content, tool_calls=None):
    message = MagicMock()
    message.type = "ai"
    message.content = content
    message.tool_calls = tool_calls or []
    return message


def _make_tool_message(name, content):
    message = MagicMock()
    message.type = "tool"
    message.name = name
    message.content = content
    return message


def _perfect_agent():
    agent = MagicMock()

    def invoke(payload):
        query = payload["messages"][0]["content"]
        mentioned = [instrument_id for instrument_id in EXPECTED if instrument_id in query]

        messages = []
        tool_calls = [
            {
                "name": "escalate_to_human",
                "args": {"instrument_id": instrument_id, "reason": "test"},
            }
            for instrument_id in mentioned
            if EXPECTED[instrument_id][0] == "ESCALATE"
        ]
        if tool_calls:
            messages.append(_make_ai_message("", tool_calls=tool_calls))
            messages.extend(
                _make_tool_message("escalate_to_human", "escalated") for _ in tool_calls
            )

        lines = [
            f"{instrument_id} -> {EXPECTED[instrument_id][0]} (rule {EXPECTED[instrument_id][1]})"
            for instrument_id in mentioned
        ]
        messages.append(_make_ai_message("\n".join(lines)))
        return {"messages": messages}

    agent.invoke.side_effect = invoke
    return agent


class TestRunScenario:
    """Single-scenario scoring: pass, amber (missing escalation), and fail."""

    def test_perfect_agent_passes_all(self):
        agent = _perfect_agent()
        for scenario in load_scenarios().scenarios:
            result = run_scenario(agent, scenario)
            assert result.status == "pass", result.notes

    def test_missing_escalate_call_is_amber(self):
        agent = MagicMock()
        agent.invoke.return_value = {"messages": [_make_ai_message("NVDA.OQ -> ESCALATE (rule 1)")]}
        scenario = next(
            item for item in load_scenarios().scenarios if item.id == "nvda-unexplained"
        )

        result = run_scenario(agent, scenario)

        assert result.status == "amber"
        assert result.decision_correct is True
        assert result.completeness_ok is False

    def test_wrong_decision_is_fail(self):
        agent = MagicMock()
        agent.invoke.return_value = {"messages": [_make_ai_message("NVDA.OQ -> APPROVED (rule 1)")]}
        scenario = next(
            item for item in load_scenarios().scenarios if item.id == "nvda-unexplained"
        )

        result = run_scenario(agent, scenario)

        assert result.status == "fail"
        assert result.decision_correct is False


class TestRunAllScenarios:
    """Full evaluation report: overall score and the per-rule/asset-class breakdowns."""

    def test_perfect_agent_scores_100_percent(self):
        report = run_all_scenarios(_perfect_agent())
        assert report.total == 7
        assert report.passed == 7
        assert report.score == 1.0

    def test_score_by_rule_present(self):
        report = run_all_scenarios(_perfect_agent())
        assert set(report.score_by_rule) == {"rule_1", "rule_3", "rule_5"}

    def test_score_by_asset_class_present(self):
        report = run_all_scenarios(_perfect_agent())
        assert "Equity" in report.score_by_asset_class
        assert "Bond" in report.score_by_asset_class

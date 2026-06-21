from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import price_review.api.app as api
import price_review.tools.registry as tools
from price_review.api.trace import extract_trace


def _make_ai_message(content: str, tool_calls=None):
    message = MagicMock()
    message.type = "ai"
    message.content = content
    message.tool_calls = tool_calls or []
    return message


def _make_tool_message(name: str, content: str):
    message = MagicMock()
    message.type = "tool"
    message.name = name
    message.content = content
    return message


FAKE_MESSAGES = [
    _make_ai_message("", tool_calls=[{"name": "get_validation_rules", "args": {}}]),
    _make_tool_message("get_validation_rules", "1. Variation <= 5% -> APPROVED"),
    _make_ai_message("AAPL.OQ -> APPROVED (rule 1)"),
]

FAKE_AGENT_RESULT = {"messages": FAKE_MESSAGES}


@pytest.fixture()
def client():
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = FAKE_AGENT_RESULT

    with (
        patch.object(api, "get_agent", return_value=fake_agent),
        patch(
            "price_review.tools.registry._load_prices",
            return_value={"as_of_date": "2026-06-18", "instruments": []},
        ),
    ):
        yield TestClient(api.app)


@pytest.fixture(autouse=True)
def reset_escalations():
    with tools._escalations_lock:
        tools.ESCALATIONS.clear()
    yield
    with tools._escalations_lock:
        tools.ESCALATIONS.clear()


class TestHealth:
    def test_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_has_key_field(self, client):
        assert "has_key" in client.get("/health").json()

    def test_provider_and_model_fields(self, client):
        body = client.get("/health").json()
        assert body["provider"] == "gemini"
        assert body["model"] == "gemini-2.5-flash"


class TestIndex:
    def test_returns_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestRules:
    def test_get_rules_returns_text(self, client, tmp_path, monkeypatch):
        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("Rule A\nRule B", encoding="utf-8")
        monkeypatch.setattr("price_review.paths.RULES_PATH", rules_file)
        response = client.get("/rules")
        assert response.status_code == 200
        assert "rules" in response.json()

    def test_post_rules_saves_and_returns_saved(self, client, tmp_path, monkeypatch):
        rules_file = tmp_path / "rules.txt"
        rules_file.write_text("old", encoding="utf-8")
        monkeypatch.setattr("price_review.paths.RULES_PATH", rules_file)
        response = client.post("/rules", json={"rules": "new rule"})
        assert response.status_code == 200
        assert response.json()["status"] == "saved"
        assert rules_file.read_text(encoding="utf-8") == "new rule"


class TestValidate:
    def test_returns_final_answer_and_steps(self, client):
        response = client.post("/validate", json={"query": "Validate AAPL.OQ"})
        body = response.json()
        assert response.status_code == 200
        assert body["final_answer"] == "AAPL.OQ -> APPROVED (rule 1)"
        assert "steps" in body

    def test_steps_contain_call_and_result(self, client):
        steps = client.post("/validate", json={"query": "Validate AAPL.OQ"}).json()["steps"]
        kinds = {step["kind"] for step in steps}
        assert "call" in kinds
        assert "result" in kinds

    def test_agent_build_failure_returns_500(self, client):
        with patch.object(api, "get_agent", side_effect=RuntimeError("no key")):
            response = client.post("/validate", json={"query": "q"})
        assert response.status_code == 500
        assert "error" in response.json()

    def test_agent_invoke_failure_returns_500(self, client):
        bad_agent = MagicMock()
        bad_agent.invoke.side_effect = Exception("LLM timeout")
        with patch.object(api, "get_agent", return_value=bad_agent):
            response = client.post("/validate", json={"query": "q"})
        assert response.status_code == 500
        assert "error" in response.json()


class TestEscalations:
    def test_empty_initially(self, client):
        assert client.get("/escalations").json()["escalations"] == []

    def test_reflects_recorded_escalations(self, client):
        tools.escalate_to_human.invoke({"instrument_id": "AAPL.OQ", "reason": "Test"})
        data = client.get("/escalations").json()["escalations"]
        assert len(data) == 1
        assert data[0]["instrument_id"] == "AAPL.OQ"


class TestScenarios:
    def test_returns_scenario_list(self, client):
        body = client.get("/scenarios").json()
        assert body["count"] == 7
        assert len(body["scenarios"]) == body["count"]

    def test_scenario_shape(self, client):
        scenario = client.get("/scenarios").json()["scenarios"][0]
        for key in (
            "id",
            "title",
            "title_fr",
            "difficulty",
            "query",
            "teaching_note",
            "teaching_note_fr",
        ):
            assert key in scenario

    def test_featured_filter(self, client):
        for scenario in client.get("/scenarios", params={"featured": True}).json()["scenarios"]:
            assert scenario["featured"] is True


class TestExtractTrace:
    def test_extracts_final_answer(self):
        final, _ = extract_trace(FAKE_MESSAGES)
        assert final == "AAPL.OQ -> APPROVED (rule 1)"

    def test_extracts_call_step(self):
        calls = [step for step in extract_trace(FAKE_MESSAGES)[1] if step["kind"] == "call"]
        assert calls[0]["tool"] == "get_validation_rules"

    def test_extracts_result_step(self):
        results = [step for step in extract_trace(FAKE_MESSAGES)[1] if step["kind"] == "result"]
        assert "APPROVED" in results[0]["content"]

    def test_empty_messages_returns_empty(self):
        final, steps = extract_trace([])
        assert final == ""
        assert steps == []

    def test_list_content_joined(self):
        message = _make_ai_message(content=[{"text": "part1"}, {"text": "part2"}])
        final, _ = extract_trace([message])
        assert "part1" in final
        assert "part2" in final


class TestGlobalExceptionHandler:
    def test_unhandled_exception_returns_json_500(self):
        @api.app.get("/test-error-endpoint")
        def boom():
            raise RuntimeError("deliberate crash")

        safe_client = TestClient(api.app, raise_server_exceptions=False)
        response = safe_client.get("/test-error-endpoint")
        assert response.status_code == 500
        body = response.json()
        assert body["error"] == "RuntimeError"
        assert "deliberate crash" in body["detail"]

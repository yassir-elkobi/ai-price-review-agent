from price_review.orchestration.supervisor import (
    _synthesis,
    group_instruments_by_asset_class,
    run_book_review,
)


class TestGrouping:
    """Instruments are grouped by asset class ahead of the supervisor fan-out."""

    def test_groups_by_asset_class(self):
        groups = group_instruments_by_asset_class()
        assert "AAPL.OQ" in groups["Equity"]
        assert "XS1234567890" in groups["Bond"]
        assert "EURUSD" in groups["FX"]


class TestRunBookReview:
    """End-to-end book review with stubbed branches/synthesis: filtering and empty input."""

    def test_filters_and_synthesizes(self, monkeypatch):
        def fake_run_branch(payload):
            return {
                "branch_results": [
                    {
                        "asset_class": payload["asset_class"],
                        "instrument_ids": payload["instrument_ids"],
                        "final_answer": "stub",
                        "steps": [],
                    }
                ]
            }

        monkeypatch.setattr("price_review.orchestration.supervisor._run_branch", fake_run_branch)
        monkeypatch.setattr(
            "price_review.orchestration.supervisor._synthesis",
            lambda state: {"report": "stub-report"},
        )

        result = run_book_review(["AAPL.OQ"])

        assert result["report"] == "stub-report"
        assert len(result["branches"]) == 1
        assert result["branches"][0]["instrument_ids"] == ["AAPL.OQ"]
        assert result["branches"][0]["asset_class"] == "Equity"

    def test_no_match_returns_empty_without_touching_the_graph(self):
        result = run_book_review(["UNKNOWN.XX"])
        assert result["branches"] == []
        assert "No instruments matched" in result["report"]


class TestSynthesis:
    """Synthesis flattens list-shaped LLM content (e.g. Claude thinking blocks) to text."""

    def test_list_content_response_is_flattened_to_text(self, monkeypatch):
        class FakeResponse:
            content = [
                {"type": "thinking", "thinking": "internal reasoning", "signature": "abc"},
                {"type": "text", "text": "Book synthesis: 1 APPROVED, 0 ESCALATE."},
            ]

        class FakeLlm:
            def invoke(self, prompt):
                return FakeResponse()

        monkeypatch.setattr("price_review.orchestration.supervisor.build_llm", lambda: FakeLlm())

        state = {
            "branch_results": [
                {
                    "asset_class": "Equity",
                    "instrument_ids": ["AAPL.OQ"],
                    "final_answer": "AAPL.OQ -> APPROVED (rule 1)",
                    "steps": [],
                }
            ]
        }
        result = _synthesis(state)

        assert result["report"] == "Book synthesis: 1 APPROVED, 0 ESCALATE."
        assert "signature" not in result["report"]
        assert isinstance(result["report"], str)

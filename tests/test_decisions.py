from price_review.decisions import parse_decisions

KNOWN_IDS = ["AAPL.OQ", "NVDA.OQ", "XS1234567890"]


class TestParseDecisions:
    """Free-text verdict parsing: single/multiple decisions and edge cases."""

    def test_parses_single_decision(self):
        text = "AAPL.OQ -> APPROVED (rule 1)"
        results = parse_decisions(text, KNOWN_IDS)
        assert len(results) == 1
        assert results[0].instrument_id == "AAPL.OQ"
        assert results[0].decision == "APPROVED"
        assert results[0].rule_ref == 1

    def test_parses_multiple_decisions(self):
        text = "NVDA.OQ -> ESCALATE (rule 1). XS1234567890 -> REJECTED (rule 2)."
        results = {item.instrument_id: item for item in parse_decisions(text, KNOWN_IDS)}
        assert results["NVDA.OQ"].decision == "ESCALATE"
        assert results["XS1234567890"].decision == "REJECTED"
        assert results["XS1234567890"].rule_ref == 2

    def test_missing_rule_number_is_none(self):
        text = "AAPL.OQ -> APPROVED"
        result = parse_decisions(text, KNOWN_IDS)[0]
        assert result.rule_ref is None

    def test_instrument_not_mentioned_is_skipped(self):
        text = "AAPL.OQ -> APPROVED (rule 1)"
        results = parse_decisions(text, KNOWN_IDS)
        assert all(item.instrument_id != "NVDA.OQ" for item in results)

    def test_empty_text_returns_empty_list(self):
        assert parse_decisions("", KNOWN_IDS) == []

    def test_case_insensitive_decision_keyword(self):
        text = "aapl.oq -> approved (rule 1)"
        result = parse_decisions(text, KNOWN_IDS)[0]
        assert result.decision == "APPROVED"

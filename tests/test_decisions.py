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

    def test_parses_decision_far_from_instrument_mention(self):
        text = (
            "## AAPL.OQ Validation Result\n\n"
            "**Data:**\n- Daily change: -6.18%\n- Divergence: -0.1%\n- Staleness: 0 days\n\n"
            "**Rule Assessment:**\n"
            "- Rule 1: move exceeds the threshold, checked market context for a "
            "justifying event, found a high-impact earnings report explaining it.\n"
            "- Rule 4: divergence is negligible, no issue.\n"
            "- Rule 3: price is fresh, no issue.\n\n"
            "**Decision: APPROVED (Rule 1)**\nRationale: justified by a direct event."
        )
        results = parse_decisions(text, KNOWN_IDS)
        assert len(results) == 1
        assert results[0].decision == "APPROVED"
        assert results[0].rule_ref == 1

    def test_multi_instrument_table_does_not_bleed_across_rows(self):
        text = "| AAPL.OQ | +1.2% | APPROVED | Rule 1 |\n| NVDA.OQ | +7.2% | ESCALATE | Rule 1 |"
        results = {item.instrument_id: item for item in parse_decisions(text, KNOWN_IDS)}
        assert results["AAPL.OQ"].decision == "APPROVED"
        assert results["NVDA.OQ"].decision == "ESCALATE"

    def test_rule_number_prefers_proximity_to_decision(self):
        text = (
            "AAPL.OQ analysis: Rule 4 divergence is fine, Rule 3 staleness is fine, "
            "final call is Decision: APPROVED (Rule 1)."
        )
        result = parse_decisions(text, KNOWN_IDS)[0]
        assert result.decision == "APPROVED"
        assert result.rule_ref == 1

    def test_final_decision_label_overrides_earlier_candidate_verdicts(self):
        text = (
            "XS1234567890: Rule 2 (Bonds): move exceeds threshold, no credit event "
            "-> would point to REJECTED. Rule 4 (Divergence): exceeds threshold "
            "-> would point to ESCALATE. Rule 5: conflicting rules, never decide "
            "alone. Decision: ESCALATE (Rule 5)."
        )
        result = parse_decisions(text, KNOWN_IDS)[0]
        assert result.decision == "ESCALATE"
        assert result.rule_ref == 5

    def test_atomic_decision_rule_line_wins_over_nearer_unrelated_rule_mentions(self):
        text = (
            "NVDA.OQ: | Divergence | 0.23% (rule 4 OK) |\n"
            "Reasoning: no direct event, only indirect sector context.\n"
            "Decision: ESCALATE (Rule 1)."
        )
        result = parse_decisions(text, KNOWN_IDS)[0]
        assert result.decision == "ESCALATE"
        assert result.rule_ref == 1

    def test_single_instrument_answer_parsed_even_without_ticker_mention(self):
        text = "**Decision: ESCALATE (Rule 3)** - price stale for 3 business days."
        results = parse_decisions(text, ["GLEN.L"])
        assert len(results) == 1
        assert results[0].instrument_id == "GLEN.L"
        assert results[0].decision == "ESCALATE"
        assert results[0].rule_ref == 3

    def test_multi_instrument_answer_skips_when_ticker_missing(self):
        text = "Decision: ESCALATE (Rule 3) - price stale for 3 business days."
        results = parse_decisions(text, ["GLEN.L", "AAPL.OQ"])
        assert results == []

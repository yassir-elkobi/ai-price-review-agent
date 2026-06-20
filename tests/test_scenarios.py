import json

from price_review.scenarios import load_scenarios, validate_scenario_references


class TestScenarioCatalog:
    def test_loads_without_errors(self):
        assert len(load_scenarios().scenarios) >= 10

    def test_all_difficulties_represented(self):
        levels = {scenario.difficulty for scenario in load_scenarios().scenarios}
        assert levels >= {"easy", "medium", "hard", "extreme"}

    def test_every_scenario_has_query_and_note(self):
        for scenario in load_scenarios().scenarios:
            assert scenario.query.strip()
            assert scenario.title_fr.strip()
            assert scenario.teaching_note_fr.strip()

    def test_references_match_prices_json(self):
        assert validate_scenario_references() == []

    def test_all_eod_covers_every_instrument(self):
        from price_review.paths import PRICES_PATH

        all_eod = next(item for item in load_scenarios().scenarios if item.id == "all-eod")
        price_ids = {
            item["instrument_id"]
            for item in json.loads(PRICES_PATH.read_text(encoding="utf-8"))["instruments"]
        }
        outcome_ids = {outcome.instrument_id for outcome in all_eod.expected_outcomes}
        assert outcome_ids == price_ids

    def test_live_flip_scenario_has_hint(self):
        flip = next(item for item in load_scenarios().scenarios if item.id == "nvda-live-flip")
        assert flip.live_flip_hint
        assert flip.live_flip_hint_fr

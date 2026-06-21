import json

import pytest

import price_review.tools.registry as tools
from price_review.tools.registry import (
    _validate_instrument_id,
    get_market_context,
    get_price_data,
    get_validation_rules,
)

PRICES_DATA = {
    "as_of_date": "2026-06-18",
    "instruments": [
        {
            "instrument_id": "AAPL.OQ",
            "name": "Apple Inc.",
            "asset_class": "Equity",
            "currency": "USD",
            "price_today": 195.34,
            "price_prior": 193.02,
            "reference_price": 195.10,
            "pct_change": 1.20,
            "divergence_vs_reference_pct": 0.12,
            "last_update": "2026-06-18T17:30:00Z",
            "business_days_since_update": 0,
            "source": "Reuters",
        },
        {
            "instrument_id": "XS1234567890",
            "name": "TotalEnergies Bond",
            "asset_class": "Bond",
            "currency": "EUR",
            "price_today": 104.85,
            "price_prior": 96.72,
            "reference_price": 96.90,
            "pct_change": 8.41,
            "divergence_vs_reference_pct": 8.20,
            "last_update": "2026-06-18T17:05:00Z",
            "business_days_since_update": 0,
            "source": "Bloomberg",
        },
    ],
}

RULES_TEXT = "1. Variation <= 5% -> APPROVED\n2. Bond > 3% -> REJECTED"


@pytest.fixture(autouse=True)
def patch_file_loaders(monkeypatch, tmp_path):
    rules_file = tmp_path / "rules.txt"
    rules_file.write_text(RULES_TEXT, encoding="utf-8")
    monkeypatch.setattr("price_review.paths.RULES_PATH", rules_file)
    monkeypatch.setattr(tools, "_load_prices", lambda: PRICES_DATA)


@pytest.fixture(autouse=True)
def reset_escalations():
    with tools._escalations_lock:
        tools.ESCALATIONS.clear()
    yield
    with tools._escalations_lock:
        tools.ESCALATIONS.clear()


class TestValidateInstrumentId:
    def test_valid_id_returned_stripped(self):
        assert _validate_instrument_id("  AAPL.OQ  ") == "AAPL.OQ"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _validate_instrument_id("   ")

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match="too long"):
            _validate_instrument_id("X" * 65)


class TestGetPriceData:
    def test_known_instrument_returns_json(self):
        data = json.loads(get_price_data.invoke({"instrument_id": "AAPL.OQ"}))
        assert data["instrument_id"] == "AAPL.OQ"

    def test_unknown_instrument_returns_message(self):
        result = get_price_data.invoke({"instrument_id": "UNKNOWN"})
        assert "No instrument" in result


class TestGetValidationRules:
    def test_returns_rules_text(self):
        result = get_validation_rules.invoke({})
        assert "APPROVED" in result
        assert "REJECTED" in result


class TestGetMarketContext:
    def test_bond_returns_no_desk_events(self):
        result = get_market_context.invoke({"instrument_id": "XS1234567890"})
        assert "No market events on record" in result

    def test_tsla_returns_earnings_fixture(self):
        result = get_market_context.invoke({"instrument_id": "TSLA.OQ"})
        assert "earnings" in result.lower()


class TestEscalateToHuman:
    def test_escalation_recorded(self):
        tools.escalate_to_human.invoke({"instrument_id": "AAPL.OQ", "reason": "Ambiguous"})
        snapshot = tools.get_escalations_snapshot()
        assert snapshot[0]["instrument_id"] == "AAPL.OQ"

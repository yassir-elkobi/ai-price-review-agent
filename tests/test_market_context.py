from unittest.mock import patch

import pytest

import price_review.market.context as market_context
from price_review.config import Settings


@pytest.fixture(autouse=True)
def reset_cache():
    market_context.clear_market_context_cache()
    yield
    market_context.clear_market_context_cache()


class TestFinnhubEligibility:
    def test_bond_isin_not_eligible(self):
        assert market_context._finnhub_eligible("XS1234567890") is False


class TestBonds:
    def test_bond_never_calls_finnhub(self):
        with patch.object(market_context, "_fetch_finnhub_events") as fetch:
            result = market_context.get_market_context_text("XS1234567890", settings=Settings())
        fetch.assert_not_called()
        assert "No market events" in result


class TestNoFinnhubKey:
    def test_equity_without_key_returns_no_events(self):
        result = market_context.get_market_context_text("AAPL.OQ", settings=Settings())
        assert "No market events" in result


class TestFinnhubLive:
    def test_live_headlines_used_when_available(self):
        settings = Settings(finnhub_api_key="test-key")
        live = [
            {
                "date": "2026-06-20",
                "headline": "Apple unveils new product line",
                "impact": "medium",
                "type": "news",
            }
        ]
        with patch.object(market_context, "_fetch_finnhub_events", return_value=live):
            result = market_context.get_market_context_text("AAPL.OQ", settings=settings)
        assert "Apple unveils new product line" in result
        assert "Finnhub" in result

    def test_empty_finnhub_response(self):
        settings = Settings(finnhub_api_key="test-key")
        with patch.object(market_context, "_fetch_finnhub_events", return_value=[]):
            result = market_context.get_market_context_text("TSLA.OQ", settings=settings)
        assert "No market events" in result

    def test_finnhub_failure_returns_no_events(self):
        settings = Settings(finnhub_api_key="test-key")
        with patch.object(
            market_context,
            "_fetch_finnhub_events",
            side_effect=TimeoutError("network down"),
        ):
            result = market_context.get_market_context_text("TSLA.OQ", settings=settings)
        assert "No market events" in result


class TestCache:
    def test_second_call_uses_cache(self):
        settings = Settings(finnhub_api_key="test-key")
        with patch.object(
            market_context,
            "_fetch_finnhub_events",
            return_value=[
                {
                    "date": "2026-06-20",
                    "headline": "Cached headline",
                    "impact": "medium",
                    "type": "news",
                }
            ],
        ) as fetch:
            market_context.get_market_context_text("NVDA.OQ", settings=settings)
            market_context.get_market_context_text("NVDA.OQ", settings=settings)
        assert fetch.call_count == 1

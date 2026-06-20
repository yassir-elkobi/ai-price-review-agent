from unittest.mock import patch

import pytest
import price_review.market.context as market_context

from price_review.config import Settings


def desk_only_settings() -> Settings:
    return Settings(_env_file=None, optional_finnhub_api_key=None)


@pytest.fixture(autouse=True)
def reset_cache():
    market_context.clear_market_context_cache()
    yield
    market_context.clear_market_context_cache()


class TestDeskFixtures:
    def test_nvda_has_no_desk_events(self):
        result = market_context.get_market_context_text("NVDA.OQ", settings=desk_only_settings())
        assert "desk demo fixtures" in result
        assert "No market events on record" in result

    def test_tsla_has_earnings_fixture(self):
        result = market_context.get_market_context_text("TSLA.OQ", settings=desk_only_settings())
        assert "earnings" in result.lower()

    def test_bond_uses_desk_only(self):
        with patch.object(market_context, "_fetch_optional_finnhub_events") as fetch:
            result = market_context.get_market_context_text(
                "XS1234567890",
                settings=Settings(_env_file=None, optional_finnhub_api_key="test-key"),
            )
        fetch.assert_not_called()
        assert "desk demo fixtures" in result


class TestOptionalFinnhubDisabled:
    def test_equity_without_key_uses_desk_only(self):
        result = market_context.get_market_context_text("AAPL.OQ", settings=desk_only_settings())
        assert "Optional Finnhub" not in result
        assert "desk demo fixtures" in result


class TestOptionalFinnhubEnabled:
    def test_live_headlines_appended_when_configured(self):
        settings = Settings(_env_file=None, optional_finnhub_api_key="test-key")
        live = [
            {
                "date": "2026-06-20",
                "headline": "Apple unveils new product line",
                "impact": "medium",
                "type": "news",
            }
        ]
        with patch.object(market_context, "_fetch_optional_finnhub_events", return_value=live):
            result = market_context.get_market_context_text("AAPL.OQ", settings=settings)
        assert "Optional Finnhub headlines" in result
        assert "Apple unveils new product line" in result

    def test_desk_and_optional_finnhub_merged(self):
        settings = Settings(_env_file=None, optional_finnhub_api_key="test-key")
        live = [
            {
                "date": "2026-06-20",
                "headline": "Generic Tesla headline",
                "impact": "medium",
                "type": "news",
            }
        ]
        with patch.object(market_context, "_fetch_optional_finnhub_events", return_value=live):
            result = market_context.get_market_context_text("TSLA.OQ", settings=settings)
        assert "Desk notes (demo fixtures):" in result
        assert "earnings" in result.lower()
        assert "Optional Finnhub headlines" in result

    def test_optional_finnhub_failure_falls_back_to_desk(self):
        settings = Settings(_env_file=None, optional_finnhub_api_key="test-key")
        with patch.object(
                market_context,
                "_fetch_optional_finnhub_events",
                side_effect=TimeoutError("network down"),
        ):
            result = market_context.get_market_context_text("TSLA.OQ", settings=settings)
        assert "desk demo fixtures" in result
        assert "earnings" in result.lower()


class TestCache:
    def test_second_call_uses_cache(self):
        settings = Settings(_env_file=None, optional_finnhub_api_key="test-key")
        with patch.object(
                market_context,
                "_fetch_optional_finnhub_events",
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

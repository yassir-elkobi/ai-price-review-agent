import pytest

import price_review.market.context as market_context


@pytest.fixture(autouse=True)
def reset_cache():
    market_context.clear_market_context_cache()
    yield
    market_context.clear_market_context_cache()


class TestDeskFixtures:
    """market_context.json fixtures return the expected per-instrument content."""

    def test_nvda_has_no_desk_events(self):
        result = market_context.get_market_context_text("NVDA.OQ")
        assert "desk demo fixtures" in result
        assert "No market events on record" in result

    def test_tsla_has_earnings_fixture(self):
        result = market_context.get_market_context_text("TSLA.OQ")
        assert "earnings" in result.lower()

    def test_eurusd_has_ecb_fixture(self):
        result = market_context.get_market_context_text("EURUSD")
        assert "ECB" in result


class TestCache:
    """Repeated lookups for the same instrument hit the in-process cache."""

    def test_second_call_uses_cache(self):
        market_context.get_market_context_text("NVDA.OQ")
        market_context.get_market_context_text("NVDA.OQ")
        assert len(market_context._cache) == 1

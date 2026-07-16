from price_review.prices import (
    group_instruments_by_asset_class,
    load_asset_class_map,
    load_instrument_ids,
    load_prices,
)


class TestPrices:
    """Shared prices.json reader: raw data, ids, and asset-class groupings."""

    def test_load_prices_returns_instruments(self):
        data = load_prices()
        assert data["instruments"]
        assert all("instrument_id" in item for item in data["instruments"])

    def test_load_instrument_ids_matches_prices_json(self):
        ids = load_instrument_ids()
        data = load_prices()
        assert ids == {item["instrument_id"] for item in data["instruments"]}

    def test_load_asset_class_map_matches_prices_json(self):
        mapping = load_asset_class_map()
        data = load_prices()
        for item in data["instruments"]:
            assert mapping[item["instrument_id"]] == item["asset_class"]

    def test_group_instruments_by_asset_class_covers_every_instrument(self):
        groups = group_instruments_by_asset_class()
        grouped_ids = {iid for ids in groups.values() for iid in ids}
        assert grouped_ids == load_instrument_ids()

    def test_group_instruments_by_asset_class_has_equity_bucket(self):
        groups = group_instruments_by_asset_class()
        assert "Equity" in groups
        assert groups["Equity"]

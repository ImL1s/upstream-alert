"""Tests for Yahoo Finance commodity futures source."""

import sys
from unittest.mock import MagicMock, patch


from upstream_alert.sources.yahoo_finance import (
    TICKER_MAP,
    _match_ticker,
    fetch_daily_prices,
    supported_keywords,
    to_signals,
)


class TestTickerMapping:
    def test_exact_keyword(self):
        assert _match_ticker("copper") == "HG=F"
        assert _match_ticker("aluminum") == "ALI=F"
        assert _match_ticker("soybean") == "ZS=F"
        assert _match_ticker("cotton") == "CT=F"
        assert _match_ticker("coffee") == "KC=F"

    def test_case_insensitive(self):
        assert _match_ticker("COPPER") == "HG=F"
        assert _match_ticker("Soybean") == "ZS=F"

    def test_partial_match(self):
        assert _match_ticker("copper_wire") == "HG=F"
        assert _match_ticker("cotton_yarn") == "CT=F"

    def test_cjk_keywords(self):
        assert _match_ticker("銅") == "HG=F"
        assert _match_ticker("鋁") == "ALI=F"
        assert _match_ticker("黃豆") == "ZS=F"
        assert _match_ticker("棉") == "CT=F"
        assert _match_ticker("咖啡") == "KC=F"
        assert _match_ticker("咖啡豆") == "KC=F"

    def test_unsupported(self):
        assert _match_ticker("steel") is None
        assert _match_ticker("rubber") is None
        assert _match_ticker("") is None


class TestFetchDailyPrices:
    def test_unsupported_item_returns_empty(self):
        result = fetch_daily_prices("unknown_item")
        assert result == []

    def test_returns_records_with_correct_shape(self):
        """Mock yfinance to return known data."""
        import pandas as pd

        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker

        idx = pd.DatetimeIndex(
            ["2026-03-15", "2026-03-16", "2026-03-17"],
            name="Date",
        )
        hist_df = pd.DataFrame(
            {"Close": [5.47, 5.50, 5.55]},
            index=idx,
        )
        mock_ticker.history.return_value = hist_df

        with patch.dict(sys.modules, {"yfinance": mock_yf}):
            result = fetch_daily_prices("copper")

        assert len(result) == 3
        assert result[0]["source"] == "yahoo"
        assert result[0]["ticker"] == "HG=F"
        assert result[0]["value"] == 5.47
        assert result[0]["date"] == "2026-03-15"

    def test_timeout_returns_empty(self):
        """Verify that fetch_daily_prices returns [] on timeout."""
        from concurrent.futures import TimeoutError as FuturesTimeout

        with patch(
            "upstream_alert.sources.yahoo_finance._fetch_impl",
            side_effect=FuturesTimeout("timed out"),
        ):
            # _match_ticker needs to find a valid ticker first
            result = fetch_daily_prices("copper")

        assert result == []


class TestToSignals:
    def test_converts_records(self):
        records = [
            {"date": "2026-03-16", "value": 5.47, "source": "yahoo", "ticker": "HG=F"},
        ]
        signals = to_signals(records)
        assert len(signals) == 1
        assert signals[0].source == "yahoo"
        assert signals[0].index_value == 5.47
        assert signals[0].category == "commodity_futures"


class TestSupportedKeywords:
    def test_returns_all_keys(self):
        keywords = supported_keywords()
        assert set(keywords) == set(TICKER_MAP.keys())


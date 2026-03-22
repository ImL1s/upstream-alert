"""Unit tests for individual source adapters.

Uses `responses` to mock HTTP calls — zero real network required.
Tests data parsing, error handling, and signal conversion.
"""

import responses
import pytest

from upstream_alert.models import FreightSignal, NewsSignal, PriceSignal


# ── FRED ──


class TestFred:
    @responses.activate
    def test_fetch_observations_parses_correctly(self):
        """FRED raw response → list of dicts with correct fields."""
        responses.add(
            responses.GET,
            "https://api.stlouisfed.org/fred/series/observations",
            json={
                "observations": [
                    {"date": "2026-02-01", "value": "310.5"},
                    {"date": "2026-01-01", "value": "308.0"},
                    {"date": "2025-02-01", "value": "300.0"},
                ]
            },
            status=200,
        )
        from upstream_alert.sources import fred

        records = fred.fetch_observations("fake-key", "CPIAUCSL", limit=3)
        assert len(records) == 3
        assert records[0]["date"] == "2026-02-01"
        assert records[0]["value"] == 310.5
        assert records[0]["source"] == "fred"
        assert records[0]["series_id"] == "CPIAUCSL"

    @responses.activate
    def test_fetch_observations_skips_missing_values(self):
        """FRED uses '.' for missing data — those should be skipped."""
        responses.add(
            responses.GET,
            "https://api.stlouisfed.org/fred/series/observations",
            json={"observations": [
                {"date": "2026-01-01", "value": "."},
                {"date": "2025-12-01", "value": "100.0"},
            ]},
            status=200,
        )
        from upstream_alert.sources import fred

        records = fred.fetch_observations("key", "X", limit=2)
        assert len(records) == 1
        assert records[0]["value"] == 100.0

    @responses.activate
    def test_fetch_observations_network_error(self):
        """Should return empty list on HTTP errors, not crash."""
        responses.add(
            responses.GET,
            "https://api.stlouisfed.org/fred/series/observations",
            status=500,
        )
        from upstream_alert.sources import fred

        records = fred.fetch_observations("key", "CPIAUCSL")
        assert records == []

    def test_to_signals_pct_change_series(self):
        """For PCT_CHANGE_SERIES, yoy_change = raw value directly."""
        from upstream_alert.sources import fred

        records = [
            {"date": "2026-02", "value": 2.5, "source": "fred",
             "series_id": "TWNPCPIPCPPPT"},
        ]
        signals = fred.to_signals(records)
        assert len(signals) == 1
        assert signals[0].yoy_change == 2.5
        assert isinstance(signals[0], PriceSignal)

    def test_to_signals_index_series_calculates_yoy(self):
        """For non-PCT series (e.g. CPIAUCSL), YoY is computed from index values."""
        from upstream_alert.sources import fred

        # 13 records: index 100 → 105, 5% increase
        records = [{"date": f"d{i}", "value": 105.0 if i == 0 else 100.0,
                     "source": "fred", "series_id": "CPIAUCSL"}
                    for i in range(13)]
        signals = fred.to_signals(records)
        assert signals[0].yoy_change == 5.0

    def test_get_latest_cpi_change_pct_series(self):
        """Taiwan CPI series returns value directly."""
        import responses as r_lib
        from upstream_alert.sources import fred

        with r_lib.RequestsMock() as rsps:
            rsps.add(
                rsps.GET,
                "https://api.stlouisfed.org/fred/series/observations",
                json={"observations": [{"date": "2026-02", "value": "3.14"}]},
                status=200,
            )
            result = fred.get_latest_cpi_change("key", "TWNPCPIPCPPPT")
            assert result == 3.14

    def test_country_series_mapping(self):
        """Verify key countries have CPI series mapped."""
        from upstream_alert.sources import fred

        assert "TW" in fred.COUNTRY_SERIES
        assert "cpi" in fred.COUNTRY_SERIES["TW"]
        assert "US" in fred.COUNTRY_SERIES
        assert "JP" in fred.COUNTRY_SERIES


# ── GDELT ──


class TestGdelt:
    @responses.activate
    def test_search_articles_parses_json(self):
        responses.add(
            responses.GET,
            "https://api.gdeltproject.org/api/v2/doc/doc",
            json={"articles": [
                {"title": "Supply chain disrupted",
                 "url": "https://example.com/1",
                 "domain": "reuters.com",
                 "seendate": "20260322",
                 "tone": "-3.5,2.1,5.6"},
            ]},
            status=200,
        )
        from upstream_alert.sources import gdelt

        articles = gdelt.search_articles("coffee supply chain")
        assert len(articles) == 1
        assert articles[0]["title"] == "Supply chain disrupted"

    @responses.activate
    def test_search_articles_rate_limited(self):
        """429 should return empty, not raise."""
        responses.add(
            responses.GET,
            "https://api.gdeltproject.org/api/v2/doc/doc",
            status=429,
        )
        from upstream_alert.sources import gdelt

        articles = gdelt.search_articles("anything")
        assert articles == []

    def test_to_signals_normalizes_tone(self):
        """GDELT tone is raw float string — should normalize to [-1, 1]."""
        from upstream_alert.sources import gdelt

        articles = [
            {"title": "Good news", "tone": "5.0", "domain": "bbc.com",
             "url": "http://x", "seendate": "20260322"},
            {"title": "Bad news", "tone": "-15.0,2.0", "domain": "cnn.com",
             "url": "http://y", "seendate": "20260322"},
        ]
        signals = gdelt.to_signals(articles)
        assert len(signals) == 2
        # tone/10, clamped to [-1, 1]
        assert signals[0].sentiment == 0.5
        assert signals[1].sentiment == -1.0  # clamped from -1.5
        assert isinstance(signals[0], NewsSignal)


# ── World Bank ──


class TestWorldBank:
    @responses.activate
    def test_fetch_indicator_parses_response(self):
        """World Bank returns [meta, [data...]] format."""
        responses.add(
            responses.GET,
            "https://api.worldbank.org/v2/country/JPN/indicator/FP.CPI.TOTL.ZG",
            json=[
                {"page": 1, "total": 1},
                [{"date": "2025", "value": 2.8, "country": {"id": "JPN"}}],
            ],
            status=200,
        )
        from upstream_alert.sources import worldbank

        records = worldbank.fetch_indicator("JP", "cpi", limit=1)
        assert len(records) == 1
        assert records[0]["value"] == 2.8
        assert records[0]["source"] == "worldbank"

    @responses.activate
    def test_fetch_indicator_empty_for_taiwan(self):
        """Taiwan is not in World Bank — should return empty."""
        responses.add(
            responses.GET,
            "https://api.worldbank.org/v2/country/TWN/indicator/FP.CPI.TOTL.ZG",
            json=[{"message": [{"key": "Invalid value"}]}],
            status=200,
        )
        from upstream_alert.sources import worldbank

        records = worldbank.fetch_indicator("TW", "cpi")
        assert records == []

    def test_to_signals_converts_correctly(self):
        from upstream_alert.sources import worldbank

        records = [{"date": "2025", "value": 3.0, "country": "JPN",
                     "indicator": "FP.CPI.TOTL.ZG", "source": "worldbank"}]
        signals = worldbank.to_signals(records)
        assert len(signals) == 1
        assert isinstance(signals[0], PriceSignal)
        assert signals[0].category == "CPI"

    def test_iso2_to_iso3_mapping(self):
        from upstream_alert.sources import worldbank

        assert worldbank._ISO2_TO_ISO3["TW"] == "TWN"
        assert worldbank._ISO2_TO_ISO3["US"] == "USA"


# ── NewsData ──


class TestNewsData:
    @responses.activate
    def test_search_news_parses_results(self):
        responses.add(
            responses.GET,
            "https://newsdata.io/api/1/latest",
            json={"results": [
                {"title": "Oil prices rising",
                 "link": "https://example.com",
                 "source_name": "Reuters",
                 "pubDate": "2026-03-22",
                 "sentiment": "negative"},
            ]},
            status=200,
        )
        from upstream_alert.sources import newsdata

        articles = newsdata.search_news("key", "oil supply chain")
        assert len(articles) == 1
        assert articles[0]["title"] == "Oil prices rising"

    def test_to_signals_sentiment_mapping(self):
        """String sentiment → float mapping."""
        from upstream_alert.sources import newsdata

        articles = [
            {"title": "A", "sentiment": "positive"},
            {"title": "B", "sentiment": "negative"},
            {"title": "C", "sentiment": "neutral"},
            {"title": "D", "sentiment": None},
            {"title": "E", "sentiment": 0.75},
        ]
        signals = newsdata.to_signals(articles)
        assert signals[0].sentiment == 0.5
        assert signals[1].sentiment == -0.5
        assert signals[2].sentiment == 0.0
        assert signals[3].sentiment == 0.0
        assert signals[4].sentiment == 0.75


# ── FBX ──


class TestFbx:
    def test_mock_fallback_when_no_key(self):
        """Without API key, should return mock data, not crash."""
        from upstream_alert.sources import fbx

        signal = fbx.fetch_global_index(api_key=None)
        assert isinstance(signal, FreightSignal)
        assert signal.source == "mock"
        assert signal.index > 0

    @responses.activate
    def test_live_api_success(self):
        responses.add(
            responses.GET,
            "https://fbx.freightos.com/api/v1/index/global",
            json={"index": 3000, "change_pct": 8.2, "date": "2026-03-22"},
            status=200,
        )
        from upstream_alert.sources import fbx

        signal = fbx.fetch_global_index(api_key="real-key")
        assert signal.source == "fbx"
        assert signal.index == 3000
        assert signal.change_pct == 8.2

    @responses.activate
    def test_api_error_falls_back_to_mock(self):
        responses.add(
            responses.GET,
            "https://fbx.freightos.com/api/v1/index/global",
            status=503,
        )
        from upstream_alert.sources import fbx

        signal = fbx.fetch_global_index(api_key="key")
        assert signal.source == "mock"


# ── Comtrade ──


class TestComtrade:
    @responses.activate
    def test_fetch_trade_data_success(self):
        responses.add(
            responses.GET,
            "https://comtradeapi.un.org/data/v1/get/C/A/HS",
            json={"data": [
                {"reporterISO": "JPN", "partnerDesc": "World",
                 "flowCode": "M", "cmdDesc": "Coffee",
                 "cmdCode": "0901", "primaryValue": 500000,
                 "qty": 1000, "period": "202501"},
            ]},
            status=200,
        )
        from upstream_alert.sources import comtrade

        records = comtrade.fetch_trade_data("key", "JP", "0901")
        assert len(records) == 1
        assert records[0]["reporterISO"] == "JPN"

    def test_unknown_reporter_returns_empty(self):
        """Country without M49 reporter code should return empty."""
        from upstream_alert.sources import comtrade

        records = comtrade.fetch_trade_data("key", "ZZ", "0901")
        assert records == []

    def test_to_signals_convert(self):
        from upstream_alert.sources import comtrade

        records = [{"reporterISO": "USA", "partnerDesc": "China",
                     "flowCode": "X", "cmdDesc": "Steel",
                     "cmdCode": "7206", "primaryValue": 999,
                     "qty": 50, "period": "202412"}]
        signals = comtrade.to_signals(records)
        assert len(signals) == 1
        assert signals[0].flow == "X"
        assert signals[0].value_usd == 999

    def test_hs_codes_table(self):
        from upstream_alert.sources import comtrade

        assert "coffee" in comtrade.HS_CODES
        assert comtrade.HS_CODES["coffee"] == "0901"
        assert "semiconductors" in comtrade.HS_CODES

    @responses.activate
    def test_fetch_trade_data_empty_data_array(self):
        """API returns 200 with empty data array → empty list, no crash."""
        responses.add(
            responses.GET,
            "https://comtradeapi.un.org/data/v1/get/C/A/HS",
            json={"data": []},
            status=200,
        )
        from upstream_alert.sources import comtrade

        records = comtrade.fetch_trade_data("key", "JP", "0901")
        assert records == []

    @responses.activate
    def test_fetch_trade_data_timeout(self):
        """Connection timeout → empty list, not exception."""
        import requests as req

        responses.add(
            responses.GET,
            "https://comtradeapi.un.org/data/v1/get/C/A/HS",
            body=req.exceptions.ConnectionError("timeout"),
        )
        from upstream_alert.sources import comtrade

        records = comtrade.fetch_trade_data("key", "US", "0901")
        assert records == []

    def test_to_signals_missing_fields(self):
        """Records with missing optional fields should use defaults."""
        from upstream_alert.sources import comtrade

        records = [{"flowCode": "M"}]  # minimal record, most fields missing
        signals = comtrade.to_signals(records)
        assert len(signals) == 1
        assert signals[0].reporter == ""
        assert signals[0].commodity == ""
        assert signals[0].value_usd == 0
        assert signals[0].quantity == 0

    def test_to_signals_null_values(self):
        """primaryValue and qty can be None from API → should default to 0."""
        from upstream_alert.sources import comtrade

        records = [{"flowCode": "X", "primaryValue": None, "qty": None}]
        signals = comtrade.to_signals(records)
        assert signals[0].value_usd == 0
        assert signals[0].quantity == 0

    @responses.activate
    def test_fetch_trade_data_malformed_json(self):
        """Non-JSON 200 response → empty list."""
        responses.add(
            responses.GET,
            "https://comtradeapi.un.org/data/v1/get/C/A/HS",
            body="NOT JSON AT ALL",
            status=200,
            content_type="text/html",
        )
        from upstream_alert.sources import comtrade

        records = comtrade.fetch_trade_data("key", "JP", "0901")
        assert records == []


# ── Edge Cases: FRED ──


class TestFredEdgeCases:
    @responses.activate
    def test_timeout_returns_empty(self):
        """Connection error → empty list."""
        import requests as req

        responses.add(
            responses.GET,
            "https://api.stlouisfed.org/fred/series/observations",
            body=req.exceptions.Timeout("read timed out"),
        )
        from upstream_alert.sources import fred

        records = fred.fetch_observations("key", "CPIAUCSL")
        assert records == []

    @responses.activate
    def test_malformed_json_response(self):
        """Non-JSON 200 → empty list."""
        responses.add(
            responses.GET,
            "https://api.stlouisfed.org/fred/series/observations",
            body="<html>Error</html>",
            status=200,
            content_type="text/html",
        )
        from upstream_alert.sources import fred

        records = fred.fetch_observations("key", "X")
        assert records == []

    @responses.activate
    def test_non_numeric_value_skipped(self):
        """Values that can't be parsed as float should be skipped."""
        responses.add(
            responses.GET,
            "https://api.stlouisfed.org/fred/series/observations",
            json={"observations": [
                {"date": "2026-01-01", "value": "not_a_number"},
                {"date": "2025-12-01", "value": "100.0"},
            ]},
            status=200,
        )
        from upstream_alert.sources import fred

        records = fred.fetch_observations("key", "X", limit=2)
        assert len(records) == 1
        assert records[0]["value"] == 100.0

    def test_to_signals_empty_records(self):
        """Empty records list → empty signals list."""
        from upstream_alert.sources import fred

        signals = fred.to_signals([])
        assert signals == []

    @responses.activate
    def test_get_latest_cpi_change_no_data(self):
        """If FRED returns no observations, should return 0.0."""
        responses.add(
            responses.GET,
            "https://api.stlouisfed.org/fred/series/observations",
            json={"observations": []},
            status=200,
        )
        from upstream_alert.sources import fred

        result = fred.get_latest_cpi_change("key", "CPIAUCSL")
        assert result == 0.0

    @responses.activate
    def test_get_latest_cpi_index_insufficient_data(self):
        """Less than 13 records for index series → 0.0."""
        responses.add(
            responses.GET,
            "https://api.stlouisfed.org/fred/series/observations",
            json={"observations": [
                {"date": "2026-01-01", "value": "100.0"},
            ]},
            status=200,
        )
        from upstream_alert.sources import fred

        result = fred.get_latest_cpi_change("key", "CPIAUCSL")
        assert result == 0.0


# ── Edge Cases: GDELT ──


class TestGdeltEdgeCases:
    @responses.activate
    def test_empty_articles_array(self):
        """articles key present but empty → empty list."""
        responses.add(
            responses.GET,
            "https://api.gdeltproject.org/api/v2/doc/doc",
            json={"articles": []},
            status=200,
        )
        from upstream_alert.sources import gdelt

        articles = gdelt.search_articles("coffee")
        assert articles == []

    @responses.activate
    def test_network_error(self):
        """Connection error → empty list, not crash."""
        import requests as req

        responses.add(
            responses.GET,
            "https://api.gdeltproject.org/api/v2/doc/doc",
            body=req.exceptions.ConnectionError("DNS failed"),
        )
        from upstream_alert.sources import gdelt

        articles = gdelt.search_articles("anything")
        assert articles == []

    def test_to_signals_missing_tone(self):
        """Article without tone field → sentiment 0.0."""
        from upstream_alert.sources import gdelt

        articles = [{"title": "Test", "url": "http://x", "domain": "x.com"}]
        signals = gdelt.to_signals(articles)
        assert signals[0].sentiment == 0.0

    def test_to_signals_empty_tone_string(self):
        """Empty tone string → 0.0."""
        from upstream_alert.sources import gdelt

        articles = [{"title": "Test", "tone": "", "url": "http://x"}]
        signals = gdelt.to_signals(articles)
        assert signals[0].sentiment == 0.0

    def test_to_signals_invalid_tone(self):
        """Non-numeric tone → 0.0."""
        from upstream_alert.sources import gdelt

        articles = [{"title": "Test", "tone": "invalid", "url": "http://x"}]
        signals = gdelt.to_signals(articles)
        assert signals[0].sentiment == 0.0


# ── Edge Cases: World Bank ──


class TestWorldBankEdgeCases:
    @responses.activate
    def test_network_error(self):
        """Connection error → empty list."""
        import requests as req

        responses.add(
            responses.GET,
            "https://api.worldbank.org/v2/country/USA/indicator/FP.CPI.TOTL.ZG",
            body=req.exceptions.ConnectionError("timeout"),
        )
        from upstream_alert.sources import worldbank

        records = worldbank.fetch_indicator("US", "cpi")
        assert records == []

    @responses.activate
    def test_null_values_skipped(self):
        """Entries with value=null are skipped."""
        responses.add(
            responses.GET,
            "https://api.worldbank.org/v2/country/JPN/indicator/FP.CPI.TOTL.ZG",
            json=[
                {"page": 1, "total": 2},
                [
                    {"date": "2025", "value": None, "country": {"id": "JPN"}},
                    {"date": "2024", "value": 2.1, "country": {"id": "JPN"}},
                ],
            ],
            status=200,
        )
        from upstream_alert.sources import worldbank

        records = worldbank.fetch_indicator("JP", "cpi")
        assert len(records) == 1
        assert records[0]["value"] == 2.1

    @responses.activate
    def test_malformed_json_response(self):
        """Non-list response → empty list."""
        responses.add(
            responses.GET,
            "https://api.worldbank.org/v2/country/USA/indicator/FP.CPI.TOTL.ZG",
            json={"error": "something broke"},
            status=200,
        )
        from upstream_alert.sources import worldbank

        records = worldbank.fetch_indicator("US", "cpi")
        assert records == []

    @responses.activate
    def test_get_latest_cpi_no_data(self):
        """No data → 0.0."""
        responses.add(
            responses.GET,
            "https://api.worldbank.org/v2/country/TWN/indicator/FP.CPI.TOTL.ZG",
            json=[{"page": 1, "total": 0}, None],
            status=200,
        )
        from upstream_alert.sources import worldbank

        result = worldbank.get_latest_cpi("TW")
        assert result == 0.0

    def test_to_signals_empty(self):
        from upstream_alert.sources import worldbank

        signals = worldbank.to_signals([])
        assert signals == []


# ── Edge Cases: NewsData ──


class TestNewsDataEdgeCases:
    @responses.activate
    def test_api_error_returns_empty(self):
        """HTTP error → empty list, not crash."""
        responses.add(
            responses.GET,
            "https://newsdata.io/api/1/latest",
            status=403,
        )
        from upstream_alert.sources import newsdata

        articles = newsdata.search_news("key", "coffee")
        assert articles == []

    @responses.activate
    def test_timeout_returns_empty(self):
        """Connection timeout → empty list."""
        import requests as req

        responses.add(
            responses.GET,
            "https://newsdata.io/api/1/latest",
            body=req.exceptions.Timeout("read timed out"),
        )
        from upstream_alert.sources import newsdata

        articles = newsdata.search_news("key", "coffee")
        assert articles == []

    @responses.activate
    def test_search_supply_chain_builds_query(self):
        """Convenience function combines 'supply chain' + item name."""
        responses.add(
            responses.GET,
            "https://newsdata.io/api/1/latest",
            json={"results": [{"title": "Match"}]},
            status=200,
        )
        from upstream_alert.sources import newsdata

        articles = newsdata.search_supply_chain("key", item_name="coffee")
        assert len(articles) == 1
        # Verify the query was built correctly
        assert "supply+chain" in responses.calls[0].request.url or \
               "supply%20chain" in responses.calls[0].request.url

    def test_to_signals_unknown_sentiment_string(self):
        """Unknown sentiment string → 0.0."""
        from upstream_alert.sources import newsdata

        articles = [{"title": "X", "sentiment": "ambiguous"}]
        signals = newsdata.to_signals(articles)
        assert signals[0].sentiment == 0.0

    def test_to_signals_missing_all_fields(self):
        """Article with no fields → uses defaults."""
        from upstream_alert.sources import newsdata

        articles = [{}]
        signals = newsdata.to_signals(articles)
        assert len(signals) == 1
        assert signals[0].title == ""
        assert signals[0].url == ""
        assert signals[0].sentiment == 0.0


# ── Edge Cases: FBX ──


class TestFbxEdgeCases:
    @responses.activate
    def test_timeout_falls_back_to_mock(self):
        """Connection timeout → mock data."""
        import requests as req

        responses.add(
            responses.GET,
            "https://fbx.freightos.com/api/v1/index/global",
            body=req.exceptions.Timeout("connect timed out"),
        )
        from upstream_alert.sources import fbx

        signal = fbx.fetch_global_index(api_key="key")
        assert signal.source == "mock"

    @responses.activate
    def test_api_returns_partial_data(self):
        """API returns JSON missing some fields → defaults used."""
        responses.add(
            responses.GET,
            "https://fbx.freightos.com/api/v1/index/global",
            json={"index": 4000},  # missing change_pct, date
            status=200,
        )
        from upstream_alert.sources import fbx

        signal = fbx.fetch_global_index(api_key="key")
        assert signal.source == "fbx"
        assert signal.index == 4000
        assert signal.change_pct == 0  # default from get()

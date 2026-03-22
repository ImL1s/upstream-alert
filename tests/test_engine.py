"""Unit tests for engine.py and analyzer.py.

Uses monkeypatching to isolate the engine from real APIs.
Tests scoring logic, data collection orchestration, and AI fallback.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from upstream_alert.engine import RiskEngine, _guess_hs_code, check_risk
from upstream_alert.models import FreightSignal, RiskLevel, RiskResult


# ── _guess_hs_code ──


class TestGuessHsCode:
    @pytest.mark.parametrize(
        "item, expected",
        [
            ("coffee", "0901"),
            ("Coffee Beans", "0901"),
            ("咖啡豆", "0901"),
            ("tea", "0902"),
            ("茶", "0902"),
            ("rice", "1006"),
            ("米", "1006"),
            ("wheat", "1001"),
            ("小麥", "1001"),
            ("gold", "7108"),
            ("steel", "7206"),
            ("semiconductor", "8542"),
            ("chip", "8542"),
            ("半導體", "8542"),
            ("automobile", "8703"),
            ("unknown_item", "0901"),  # default fallback
        ],
    )
    def test_item_name_to_hs_code(self, item: str, expected: str):
        assert _guess_hs_code(item) == expected

    def test_case_insensitive(self):
        assert _guess_hs_code("COFFEE") == "0901"
        assert _guess_hs_code("  Steel  ") == "7206"


# ── RiskEngine._calculate_score ──


class TestCalculateScore:
    """Test scoring logic in isolation."""

    def _engine(self) -> RiskEngine:
        return RiskEngine(
            fred_key="", comtrade_key="", newsdata_key="",
            gemini_key="", fbx_key="",
        )

    def test_no_data_gives_base_score(self):
        """With zero data, should still return a valid score (uncertainty penalty)."""
        e = self._engine()
        score = e._calculate_score([], [], None, [])
        # No CPI=0, no news=0, no freight=0, no trade=+10 (uncertainty)
        assert score == 10

    def test_high_cpi_inflates_score(self):
        e = self._engine()
        price = [{"yoy_change": 6.0}]  # >5 → +30
        score = e._calculate_score(price, [], None, [])
        # 30 (CPI) + 10 (no trade) = 40
        assert score == 40

    def test_moderate_cpi(self):
        e = self._engine()
        price = [{"yoy_change": 3.5}]  # >3 → +20
        score = e._calculate_score(price, [], None, [])
        assert score == 30  # 20 + 10

    def test_negative_news_sentiment_increases_score(self):
        e = self._engine()
        news = [
            {"sentiment": -0.5},
            {"sentiment": -0.3},
            {"sentiment": 0.2},
        ]
        # 2/3 negative → ratio=0.667 → 0.667*60=40 → capped at 30
        score = e._calculate_score([], news, None, [])
        assert 30 <= score <= 40  # 30 (news cap) + 10 (no trade)

    def test_freight_spike_increases_score(self):
        e = self._engine()
        freight = FreightSignal(index=5000, change_pct=12.0, source="fbx")
        score = e._calculate_score([], [], freight, [])
        # 0(CPI) + 0(news) + 20(freight>10%) + 10(no trade) = 30
        assert score == 30

    def test_mock_freight_ignored(self):
        """Mock freight source should not affect score."""
        e = self._engine()
        freight = FreightSignal(index=5000, change_pct=50.0, source="mock")
        score = e._calculate_score([], [], freight, [])
        # Mock freight → 0 points for freight
        assert score == 10  # just uncertainty penalty

    def test_trade_data_present_removes_uncertainty(self):
        e = self._engine()
        trade = [{"something": "data"}]
        score = e._calculate_score([], [], None, trade)
        # No CPI, no news, no freight, trade present → 0
        assert score == 0

    def test_score_clamped_to_100(self):
        """Even with all maxed signals, score should not exceed 100."""
        e = self._engine()
        price = [{"yoy_change": 10.0}]  # +30
        news = [{"sentiment": -0.9} for _ in range(10)]  # all negative → +30
        freight = FreightSignal(index=9999, change_pct=20.0, source="fbx")  # +20
        # 30 + 30 + 20 + 10 = 90, which is under 100
        score = e._calculate_score(price, news, freight, [])
        assert score <= 100

    def test_deflation_also_scores(self):
        """Negative CPI (deflation) is also a risk signal."""
        e = self._engine()
        price = [{"yoy_change": -2.0}]  # <0 → +5
        score = e._calculate_score(price, [], None, [])
        assert score == 15  # 5 + 10(no trade)


# ── RiskEngine.check (integration with mocked sources) ──


class TestEngineCheck:
    """Test engine.check() with all external calls mocked."""

    @patch("upstream_alert.analyzer.analyze_risk")
    @patch("upstream_alert.sources.gdelt.search_articles")
    @patch("upstream_alert.sources.fbx.fetch_global_index")
    @patch("upstream_alert.sources.worldbank.fetch_indicator")
    def test_check_minimal(self, mock_wb, mock_fbx, mock_gdelt, mock_ai):
        """Engine should work with zero API keys and mocked sources."""
        mock_wb.return_value = [
            {"date": "2025", "value": 2.5, "country": "JPN",
             "indicator": "FP.CPI.TOTL.ZG", "source": "worldbank"},
        ]
        mock_fbx.return_value = FreightSignal(
            index=2000, change_pct=-1.0, source="mock",
        )
        mock_gdelt.return_value = []
        mock_ai.return_value = "AI fallback summary"

        engine = RiskEngine()  # no keys
        result = engine.check("coffee", "JP")

        assert isinstance(result, RiskResult)
        assert result.item == "coffee"
        assert result.country == "JP"
        assert 0 <= result.score <= 100
        assert isinstance(result.level, RiskLevel)
        assert result.ai_summary == "AI fallback summary"
        assert "worldbank" in result.sources_used

    @patch("upstream_alert.analyzer.analyze_risk")
    @patch("upstream_alert.sources.gdelt.search_articles")
    @patch("upstream_alert.sources.fbx.fetch_global_index")
    @patch("upstream_alert.sources.worldbank.fetch_indicator")
    def test_check_all_sources_fail_gracefully(
        self, mock_wb, mock_fbx, mock_gdelt, mock_ai,
    ):
        """If every source throws, engine should still return a valid result."""
        mock_wb.side_effect = Exception("WB down")
        mock_fbx.side_effect = Exception("FBX down")
        mock_gdelt.side_effect = Exception("GDELT down")
        mock_ai.return_value = "Fallback"

        engine = RiskEngine()
        result = engine.check("rice", "TH")

        assert isinstance(result, RiskResult)
        assert result.score >= 0
        assert len(result.errors) > 0  # should have recorded errors


# ── analyzer.py ──


class TestAnalyzer:
    def test_template_summary_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        """No API key → template fallback, not crash."""
        from upstream_alert.analyzer import analyze_risk

        result = analyze_risk(
            item="coffee",
            country="TW",
            price_signals=[{"category": "CPI", "yoy_change": 4.5, "period": "2026-01"}],
            news_signals=[],
            api_key="",
        )
        assert "coffee" in result
        assert "TW" in result
        assert "4.5" in result

    def test_template_summary_with_negative_news(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from upstream_alert.analyzer import analyze_risk

        result = analyze_risk(
            item="steel",
            country="US",
            price_signals=[],
            news_signals=[
                {"title": "Tariff threat", "sentiment": -0.5},
                {"title": "Normal news", "sentiment": 0.1},
            ],
            api_key="",
        )
        assert "1 concerning" in result

    def test_template_summary_no_data(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from upstream_alert.analyzer import analyze_risk

        result = analyze_risk(
            item="unknown",
            country="ZZ",
            price_signals=[],
            news_signals=[],
            api_key="",
        )
        assert "unknown" in result

    def test_build_prompt_includes_all_sections(self):
        from upstream_alert.analyzer import _build_prompt

        prompt = _build_prompt(
            item="rice",
            country="TH",
            price_signals=[{"category": "CPI", "yoy_change": 3.0, "period": "2026-Q1"}],
            news_signals=[{"title": "Rice shortage warning"}],
            market_pulse={"freight": {"index": 2000}, "cpi_change": 3.0, "pmi": 50.1},
        )
        assert "rice" in prompt
        assert "TH" in prompt
        assert "PRICE SIGNALS" in prompt
        assert "RECENT NEWS" in prompt
        assert "MARKET PULSE" in prompt
        assert "CPI" in prompt
        assert "Rice shortage" in prompt

    def test_gemini_error_falls_back_to_template(self, monkeypatch):
        """If Gemini API throws, should gracefully fallback."""
        from upstream_alert.analyzer import analyze_risk

        # Patch genai import to raise inside the function
        import importlib
        import upstream_alert.analyzer as analyzer_mod

        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def mock_import(name, *args, **kwargs):
            if name == "google" or name == "google.genai":
                raise ImportError("no genai")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        result = analyze_risk(
            item="test",
            country="US",
            price_signals=[],
            news_signals=[],
            api_key="fake-key",
        )
        # Should not crash — falls back to template
        assert isinstance(result, str)
        assert "test" in result


# ── check_risk convenience function ──


class TestCheckRiskConvenience:
    @patch("upstream_alert.analyzer.analyze_risk")
    @patch("upstream_alert.sources.gdelt.search_articles")
    @patch("upstream_alert.sources.fbx.fetch_global_index")
    @patch("upstream_alert.sources.worldbank.fetch_indicator")
    def test_check_risk_function(self, mock_wb, mock_fbx, mock_gdelt, mock_ai):
        mock_wb.return_value = []
        mock_fbx.return_value = FreightSignal(index=1000, source="mock")
        mock_gdelt.return_value = []
        mock_ai.return_value = "Summary"

        result = check_risk("tea", country="JP")
        assert isinstance(result, RiskResult)
        assert result.item == "tea"
        assert result.country == "JP"


# ── Edge Cases: Score Boundaries ──


class TestScoreBoundaryExact:
    """Test exact boundary values for CPI scoring thresholds."""

    def _engine(self) -> RiskEngine:
        return RiskEngine(
            fred_key="", comtrade_key="", newsdata_key="",
            gemini_key="", fbx_key="",
        )

    def test_cpi_exactly_5(self):
        """CPI=5.0 is in the >3 bracket (20), not >5 bracket (30)."""
        e = self._engine()
        price = [{"yoy_change": 5.0}]
        score = e._calculate_score(price, [], None, [])
        # >3 but not >5 → 20; + 10 (no trade) = 30
        assert score == 30

    def test_cpi_exactly_3(self):
        """CPI=3.0 is in the >2 bracket (10), not >3 bracket (20)."""
        e = self._engine()
        price = [{"yoy_change": 3.0}]
        score = e._calculate_score(price, [], None, [])
        # >2 but not >3 → 10; + 10 (no trade) = 20
        assert score == 20

    def test_cpi_exactly_2(self):
        """CPI=2.0 is neither >2 nor <0 → 0 points from CPI."""
        e = self._engine()
        price = [{"yoy_change": 2.0}]
        score = e._calculate_score(price, [], None, [])
        # CPI=0 + 10 (no trade) = 10
        assert score == 10

    def test_cpi_exactly_0(self):
        """CPI=0.0 → no CPI risk points."""
        e = self._engine()
        price = [{"yoy_change": 0.0}]
        score = e._calculate_score(price, [], None, [])
        assert score == 10  # just uncertainty

    def test_all_news_negative(self):
        """All news negative → capped at 30 + uncertainty = 40."""
        e = self._engine()
        news = [{"sentiment": -0.9} for _ in range(20)]
        score = e._calculate_score([], news, None, [])
        assert score == 40  # 30 + 10

    def test_freight_moderate_change(self):
        """freight 5 < change_pct <= 10 → +15."""
        e = self._engine()
        freight = FreightSignal(index=3000, change_pct=7.0, source="fbx")
        score = e._calculate_score([], [], freight, [])
        assert score == 25  # 15 + 10

    def test_freight_small_positive_change(self):
        """freight 0 < change_pct <= 5 → +5."""
        e = self._engine()
        freight = FreightSignal(index=3000, change_pct=3.0, source="fbx")
        score = e._calculate_score([], [], freight, [])
        assert score == 15  # 5 + 10

    def test_freight_exactly_10(self):
        """freight change_pct=10.0 is >5 bracket (15), not >10 bracket (20)."""
        e = self._engine()
        freight = FreightSignal(index=3000, change_pct=10.0, source="fbx")
        score = e._calculate_score([], [], freight, [])
        assert score == 25  # 15 + 10

    def test_freight_negative_change(self):
        """freight negative change → 0 freight points."""
        e = self._engine()
        freight = FreightSignal(index=3000, change_pct=-5.0, source="fbx")
        score = e._calculate_score([], [], freight, [])
        assert score == 10  # just uncertainty

    def test_combined_max_score_without_trade(self):
        """Max score: CPI>5(30) + all_neg_news(30) + freight>10(20) + no_trade(10) = 90."""
        e = self._engine()
        price = [{"yoy_change": 8.0}]
        news = [{"sentiment": -0.9} for _ in range(10)]
        freight = FreightSignal(index=9999, change_pct=15.0, source="fbx")
        score = e._calculate_score(price, news, freight, [])
        assert score == 90

    def test_combined_max_score_with_trade(self):
        """Max with trade data: 30 + 30 + 20 + 0 = 80."""
        e = self._engine()
        price = [{"yoy_change": 8.0}]
        news = [{"sentiment": -0.9} for _ in range(10)]
        freight = FreightSignal(index=9999, change_pct=15.0, source="fbx")
        trade = [{"data": "present"}]
        score = e._calculate_score(price, news, freight, trade)
        assert score == 80


# ── Edge Cases: Engine with partial source failures ──


class TestEnginePartialSources:
    """Test engine when some sources succeed and others fail."""

    @patch("upstream_alert.analyzer.analyze_risk")
    @patch("upstream_alert.sources.gdelt.search_articles")
    @patch("upstream_alert.sources.fbx.fetch_global_index")
    @patch("upstream_alert.sources.worldbank.fetch_indicator")
    def test_worldbank_fails_gdelt_succeeds(
        self, mock_wb, mock_fbx, mock_gdelt, mock_ai,
    ):
        """WB down, GDELT works → result has GDELT data + error."""
        mock_wb.side_effect = Exception("WB API down")
        mock_fbx.return_value = FreightSignal(index=2000, source="mock")
        mock_gdelt.return_value = [
            {"title": "Supply chain news", "url": "http://x",
             "domain": "bbc.com", "tone": "-2.0", "seendate": "20260322"},
        ]
        mock_ai.return_value = "AI summary"

        engine = RiskEngine()
        result = engine.check("coffee", "JP")

        assert isinstance(result, RiskResult)
        assert any("World Bank" in e or "WB" in e for e in result.errors)
        assert "gdelt" in result.sources_used

    @patch("upstream_alert.analyzer.analyze_risk")
    @patch("upstream_alert.sources.gdelt.search_articles")
    @patch("upstream_alert.sources.fbx.fetch_global_index")
    @patch("upstream_alert.sources.worldbank.fetch_indicator")
    def test_fbx_exception_recorded(
        self, mock_wb, mock_fbx, mock_gdelt, mock_ai,
    ):
        """FBX exception → error recorded, engine continues."""
        mock_wb.return_value = []
        mock_fbx.side_effect = Exception("FBX timeout")
        mock_gdelt.return_value = []
        mock_ai.return_value = "Summary"

        engine = RiskEngine()
        result = engine.check("tea", "US")

        assert isinstance(result, RiskResult)
        assert any("FBX" in e for e in result.errors)

    @patch("upstream_alert.analyzer.analyze_risk")
    @patch("upstream_alert.sources.gdelt.search_articles")
    @patch("upstream_alert.sources.fbx.fetch_global_index")
    @patch("upstream_alert.sources.worldbank.fetch_indicator")
    def test_empty_item_name(
        self, mock_wb, mock_fbx, mock_gdelt, mock_ai,
    ):
        """Empty item name → defaults to coffee HS code, no crash."""
        mock_wb.return_value = []
        mock_fbx.return_value = FreightSignal(index=1000, source="mock")
        mock_gdelt.return_value = []
        mock_ai.return_value = "Summary"

        engine = RiskEngine()
        result = engine.check("", "US")

        assert isinstance(result, RiskResult)
        assert result.item == ""

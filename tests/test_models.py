"""Unit tests for upstream_alert.models.

Tests Pydantic model validation, serialization, and business logic
(RiskLevel.from_score, RiskResult.to_brief, to_dict).
"""

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from upstream_alert.models import (
    FreightSignal,
    MarketPulse,
    NewsSignal,
    PriceSignal,
    RiskLevel,
    RiskResult,
    TradeSignal,
)


# ── RiskLevel ──


class TestRiskLevel:
    """RiskLevel.from_score boundary tests."""

    @pytest.mark.parametrize(
        "score, expected",
        [
            (0, RiskLevel.LOW),
            (39, RiskLevel.LOW),
            (40, RiskLevel.MEDIUM),
            (59, RiskLevel.MEDIUM),
            (60, RiskLevel.HIGH),
            (79, RiskLevel.HIGH),
            (80, RiskLevel.CRITICAL),
            (100, RiskLevel.CRITICAL),
        ],
    )
    def test_from_score_boundaries(self, score: int, expected: RiskLevel):
        assert RiskLevel.from_score(score) == expected

    def test_enum_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_enum_value_strings(self):
        """RiskLevel enum values should be lowercase strings."""
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.LOW.value == "low"


# ── PriceSignal ──


class TestPriceSignal:
    def test_valid_signal(self):
        s = PriceSignal(
            source="fred", period="2026-01", category="CPI",
            index_value=301.5, yoy_change=3.2,
        )
        assert s.source == "fred"
        assert s.yoy_change == 3.2

    def test_defaults(self):
        s = PriceSignal(source="worldbank", period="2025", category="CPI")
        assert s.index_value == 0.0
        assert s.yoy_change == 0.0

    def test_serialization_roundtrip(self):
        s = PriceSignal(source="fred", period="2026-02", category="PPI",
                        index_value=100.0, yoy_change=-1.5)
        d = s.model_dump()
        s2 = PriceSignal(**d)
        assert s == s2


# ── NewsSignal ──


class TestNewsSignal:
    def test_valid_signal(self):
        n = NewsSignal(title="Supply chain crisis", url="https://example.com",
                       sentiment=-0.6)
        assert n.sentiment == -0.6

    def test_defaults(self):
        n = NewsSignal(title="Test")
        assert n.url == ""
        assert n.sentiment == 0.0
        assert n.relevance == 0.5


# ── FreightSignal ──


class TestFreightSignal:
    def test_valid(self):
        f = FreightSignal(index=2150.0, change_pct=-1.5, date="2026-03", source="fbx")
        assert f.index == 2150.0
        assert f.source == "fbx"

    def test_mock_defaults(self):
        f = FreightSignal(index=0, source="mock")
        assert f.change_pct == 0.0


# ── TradeSignal ──


class TestTradeSignal:
    def test_valid(self):
        t = TradeSignal(reporter="TWN", flow="M", commodity="Coffee",
                        hs_code="0901", value_usd=1000000)
        assert t.partner == "World"
        assert t.value_usd == 1000000


# ── MarketPulse ──


class TestMarketPulse:
    def test_with_freight(self):
        f = FreightSignal(index=2000, change_pct=5.0, source="fbx")
        p = MarketPulse(freight=f, cpi_change=3.1)
        assert p.freight is not None
        assert p.cpi_change == 3.1

    def test_without_freight(self):
        p = MarketPulse()
        assert p.freight is None
        assert p.cpi_change == 0.0


# ── RiskResult ──


class TestRiskResult:
    def _make_result(self, score: int = 25, **kwargs) -> RiskResult:
        return RiskResult(
            item="coffee",
            country="TW",
            score=score,
            level=RiskLevel.from_score(score),
            **kwargs,
        )

    def test_to_brief_format(self):
        r = self._make_result(score=25)
        brief = r.to_brief()
        assert "coffee" in brief
        assert "TW" in brief
        assert "25/100" in brief
        assert "LOW" in brief
        assert "🟢" in brief

    @pytest.mark.parametrize(
        "score, emoji, level_str",
        [
            (10, "🟢", "LOW"),
            (45, "🟡", "MEDIUM"),
            (65, "🟠", "HIGH"),
            (90, "🔴", "CRITICAL"),
        ],
    )
    def test_to_brief_emoji_per_level(self, score, emoji, level_str):
        r = self._make_result(score=score)
        brief = r.to_brief()
        assert emoji in brief
        assert level_str in brief

    def test_to_dict_is_json_serializable(self):
        r = self._make_result(
            score=50,
            ai_summary="Test summary",
            sources_used=["fred", "gdelt"],
            errors=["minor warning"],
        )
        d = r.to_dict()
        # Must not raise
        json_str = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["item"] == "coffee"
        assert parsed["score"] == 50
        assert parsed["level"] == "medium"
        assert isinstance(parsed["checked_at"], str)

    def test_score_validation_range(self):
        """Score must be 0-100 per the Pydantic constraint."""
        with pytest.raises(ValidationError):
            RiskResult(item="x", country="TW", score=101, level=RiskLevel.LOW)
        with pytest.raises(ValidationError):
            RiskResult(item="x", country="TW", score=-1, level=RiskLevel.LOW)

    def test_checked_at_is_auto_set(self):
        r = self._make_result(score=10)
        assert isinstance(r.checked_at, datetime)

    def test_unicode_item_name(self):
        """Non-ASCII item names (CJK) must round-trip correctly."""
        r = RiskResult(item="咖啡豆", country="TW", score=30,
                       level=RiskLevel.LOW)
        d = r.to_dict()
        j = json.dumps(d, ensure_ascii=False)
        assert "咖啡豆" in j
        parsed = json.loads(j)
        assert parsed["item"] == "咖啡豆"

    def test_score_boundary_zero(self):
        """Score=0 is valid."""
        r = RiskResult(item="x", country="TW", score=0, level=RiskLevel.LOW)
        assert r.score == 0

    def test_score_boundary_hundred(self):
        """Score=100 is valid."""
        r = RiskResult(item="x", country="TW", score=100,
                       level=RiskLevel.CRITICAL)
        assert r.score == 100

    def test_empty_strings(self):
        """Empty item/country should still create valid result."""
        r = RiskResult(item="", country="", score=50, level=RiskLevel.MEDIUM)
        assert r.item == ""
        assert r.country == ""
        d = r.to_dict()
        assert json.dumps(d)  # must not crash

    def test_long_ai_summary(self):
        """Very long AI summary should not cause issues."""
        long_text = "A" * 10000
        r = RiskResult(item="test", country="US", score=50,
                       level=RiskLevel.MEDIUM, ai_summary=long_text)
        d = r.to_dict()
        assert len(d["ai_summary"]) == 10000

    def test_fully_populated_json_roundtrip(self):
        """All fields filled → JSON roundtrip succeeds."""
        freight = FreightSignal(index=2500, change_pct=8.5,
                                date="2026-03", source="fbx")
        pulse = MarketPulse(
            freight=freight, cpi_change=3.5,
            trade_signals=[
                TradeSignal(reporter="JPN", flow="M", commodity="Coffee",
                            hs_code="0901", value_usd=100000, quantity=50,
                            period="202601"),
            ],
        )
        r = RiskResult(
            item="coffee", country="JP", score=65,
            level=RiskLevel.HIGH,
            ai_summary="Risk analysis summary here.",
            price_signals=[
                PriceSignal(source="fred", period="2026-02",
                            category="CPI", index_value=310, yoy_change=4.2),
            ],
            news_signals=[
                NewsSignal(title="Supply disruption", url="http://x",
                           sentiment=-0.6),
            ],
            market_pulse=pulse,
            sources_used=["fred", "gdelt", "comtrade"],
            errors=["newsdata: timeout"],
        )
        d = r.to_dict()
        j = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(j)
        assert parsed["score"] == 65
        assert parsed["level"] == "high"
        assert len(parsed["sources_used"]) == 3
        assert len(parsed["errors"]) == 1


# ── Edge Cases: PriceSignal ──


class TestPriceSignalEdgeCases:
    def test_extreme_yoy_change(self):
        """Very large YoY change should be accepted."""
        s = PriceSignal(source="test", period="2026", category="CPI",
                        yoy_change=999.99)
        assert s.yoy_change == 999.99

    def test_negative_index_value(self):
        """Negative index value (unusual but valid)."""
        s = PriceSignal(source="test", period="2026", category="CPI",
                        index_value=-5.0)
        assert s.index_value == -5.0


# ── Edge Cases: NewsSignal ──


class TestNewsSignalEdgeCases:
    def test_extreme_sentiment_values(self):
        """Extreme sentiment values should be accepted by model."""
        n1 = NewsSignal(title="Good", sentiment=1.0)
        n2 = NewsSignal(title="Bad", sentiment=-1.0)
        assert n1.sentiment == 1.0
        assert n2.sentiment == -1.0

    def test_long_title(self):
        """Very long title should not crash."""
        title = "Breaking News: " * 200
        n = NewsSignal(title=title)
        assert len(n.title) > 1000


# ── Edge Cases: TradeSignal ──


class TestTradeSignalEdgeCases:
    def test_zero_values(self):
        """Zero trade values should be valid."""
        t = TradeSignal(reporter="USA", flow="M", commodity="Test",
                        hs_code="0000", value_usd=0, quantity=0)
        assert t.value_usd == 0
        assert t.quantity == 0

    def test_large_trade_value(self):
        """Very large USD values (billion+) should work."""
        t = TradeSignal(reporter="CHN", flow="X", commodity="Electronics",
                        hs_code="8542", value_usd=50_000_000_000)
        assert t.value_usd == 50_000_000_000


# ── Edge Cases: MarketPulse ──


class TestMarketPulseEdgeCases:
    def test_with_trade_signals(self):
        """MarketPulse with trade_signals populated."""
        ts = TradeSignal(reporter="JPN", flow="M", commodity="Rice",
                         hs_code="1006", value_usd=100)
        p = MarketPulse(trade_signals=[ts], cpi_change=-2.0)
        assert len(p.trade_signals) == 1
        assert p.cpi_change == -2.0

    def test_serialization(self):
        """MarketPulse must serialize to JSON cleanly."""
        f = FreightSignal(index=3000, change_pct=12.0, source="fbx",
                          date="2026-03")
        p = MarketPulse(freight=f, cpi_change=5.5, trade_signals=[])
        d = p.model_dump()
        j = json.dumps(d)
        parsed = json.loads(j)
        assert parsed["freight"]["index"] == 3000
        assert parsed["cpi_change"] == 5.5

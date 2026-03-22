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

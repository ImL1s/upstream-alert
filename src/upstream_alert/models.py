"""Data models for upstream-alert.

All public schemas use Pydantic for validation and serialization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk severity classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def from_score(cls, score: int) -> RiskLevel:
        if score >= 80:
            return cls.CRITICAL
        if score >= 60:
            return cls.HIGH
        if score >= 40:
            return cls.MEDIUM
        return cls.LOW


class PriceSignal(BaseModel):
    """A single economic indicator data point."""

    source: str = Field(description="Data source (yahoo, fred, worldbank, comtrade)")
    period: str = Field(description="Time period (e.g. 2026-01)")
    category: str = Field(description="Signal category (CPI, PPI, trade)")
    index_value: float = Field(default=0.0, description="Raw index value")
    yoy_change: float = Field(default=0.0, description="Year-over-year % change")


class NewsSignal(BaseModel):
    """A single news article with sentiment."""

    title: str
    url: str = ""
    source_name: str = ""
    published: str = ""
    sentiment: float = Field(
        default=0.0,
        description="Sentiment score: -1.0 (negative) to 1.0 (positive)",
    )
    relevance: float = Field(
        default=0.5,
        description="Relevance score: 0.0 to 1.0",
    )


class TradeSignal(BaseModel):
    """International trade data point."""

    reporter: str = Field(description="Reporting country ISO3")
    partner: str = Field(default="World", description="Trade partner")
    flow: str = Field(description="M=import, X=export")
    commodity: str = ""
    hs_code: str = ""
    value_usd: float = 0.0
    quantity: float = 0.0
    period: str = ""


class FreightSignal(BaseModel):
    """Shipping freight index data."""

    index: float = Field(description="FBX global index value")
    change_pct: float = Field(default=0.0, description="% change")
    date: str = ""
    source: str = "fbx"


class MarketPulse(BaseModel):
    """Current market condition snapshot."""

    freight: FreightSignal | None = None
    cpi_change: float = Field(default=0.0, description="Latest CPI YoY %")
    pmi: float = Field(default=0.0, description="Manufacturing PMI")
    trade_signals: list[TradeSignal] = Field(default_factory=list)


class RiskResult(BaseModel):
    """Complete risk assessment result."""

    item: str = Field(description="Monitored item name")
    country: str = Field(default="TW", description="Country ISO2 code")
    score: int = Field(
        ge=0, le=100,
        description="Risk score 0-100, higher = more risk",
    )
    level: RiskLevel
    ai_summary: str = Field(
        default="",
        description="AI-generated analysis summary",
    )
    price_signals: list[PriceSignal] = Field(default_factory=list)
    news_signals: list[NewsSignal] = Field(default_factory=list)
    market_pulse: MarketPulse | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sources_used: list[str] = Field(default_factory=list)
    errors: list[str] = Field(
        default_factory=list,
        description="Non-fatal errors during data collection",
    )

    def to_brief(self) -> str:
        """One-line summary for CLI / chat output."""
        emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
        e = emoji.get(self.level.value, "⚪")
        return f"{e} {self.item} ({self.country}) — Score: {self.score}/100 [{self.level.value.upper()}]"

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict (for skill scripts)."""
        return self.model_dump(mode="json")

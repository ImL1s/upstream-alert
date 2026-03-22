"""Risk assessment engine — the core of upstream-alert.

Orchestrates data collection from multiple sources and produces
a unified RiskResult. Completely stateless and Firebase-free.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from upstream_alert.models import (
    FreightSignal,
    MarketPulse,
    RiskLevel,
    RiskResult,
)

logger = logging.getLogger(__name__)


class RiskEngine:
    """Supply chain risk assessment engine.

    Collects data from FRED, GDELT, Comtrade, World Bank, NewsData, and FBX,
    then scores the overall risk.

    Usage:
        engine = RiskEngine()  # reads API keys from env
        result = engine.check("咖啡豆", country="TW")
        print(result.score, result.level)
    """

    def __init__(
        self,
        fred_key: str | None = None,
        comtrade_key: str | None = None,
        newsdata_key: str | None = None,
        gemini_key: str | None = None,
        fbx_key: str | None = None,
    ):
        self._fred_key = fred_key or os.environ.get("FRED_API_KEY", "")
        self._comtrade_key = comtrade_key or os.environ.get("COMTRADE_API_KEY", "")
        self._newsdata_key = newsdata_key or os.environ.get("NEWSDATA_API_KEY", "")
        self._gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY", "")
        self._fbx_key = fbx_key or os.environ.get("FBX_API_KEY")

    def check(self, item: str, country: str = "TW") -> RiskResult:
        """Run a full risk assessment for an item in a country.

        This is the main entry point. It:
        1. Queries all available data sources
        2. Calculates a risk score (0-100)
        3. Generates an AI summary (if Gemini key available)
        4. Returns a unified RiskResult
        """
        errors: list[str] = []
        sources_used: list[str] = []

        # ── Collect data ──
        price_signals = self._collect_prices(country, errors, sources_used)
        news_signals = self._collect_news(item, country, errors, sources_used)
        freight = self._collect_freight(errors, sources_used)
        trade_signals = self._collect_trade(country, item, errors, sources_used)

        # ── Market pulse ──
        cpi_change = 0.0
        if price_signals:
            cpi_change = price_signals[0].get("yoy_change", 0.0)

        pulse = MarketPulse(
            freight=freight,
            cpi_change=cpi_change,
            trade_signals=[],
        )

        # ── Score ──
        score = self._calculate_score(
            price_signals, news_signals, freight, trade_signals,
        )
        level = RiskLevel.from_score(score)

        # ── AI analysis ──
        # Lazy import to avoid circular dependency (analyzer imports models)
        from upstream_alert.analyzer import analyze_risk

        ai_summary = analyze_risk(
            item=item,
            country=country,
            price_signals=price_signals,
            news_signals=news_signals,
            market_pulse=pulse.model_dump() if pulse else None,
            api_key=self._gemini_key,
        )

        return RiskResult(
            item=item,
            country=country,
            score=score,
            level=level,
            ai_summary=ai_summary,
            price_signals=[],  # compact output
            news_signals=[],
            market_pulse=pulse,
            sources_used=sources_used,
            errors=errors,
        )

    # ── Data collectors ──

    def _collect_prices(
        self, country: str, errors: list[str], sources: list[str],
    ) -> list[dict[str, Any]]:
        """Collect price signals (CPI) from FRED and World Bank."""
        signals: list[dict[str, Any]] = []

        # FRED
        if self._fred_key:
            try:
                from upstream_alert.sources import fred

                series_map = fred.COUNTRY_SERIES.get(country.upper(), {})
                cpi_series = series_map.get("cpi", "")
                if cpi_series:
                    records = fred.fetch_observations(
                        self._fred_key, cpi_series, limit=13,
                    )
                    signals.extend(
                        s.model_dump() for s in fred.to_signals(records)
                    )
                    if records:
                        sources.append("fred")
            except Exception as e:
                errors.append(f"FRED: {e}")

        # World Bank (free fallback)
        if not signals:
            try:
                from upstream_alert.sources import worldbank

                records = worldbank.fetch_indicator(country, "cpi", limit=5)
                signals.extend(
                    s.model_dump() for s in worldbank.to_signals(records)
                )
                if records:
                    sources.append("worldbank")
            except Exception as e:
                errors.append(f"WorldBank: {e}")

        return signals

    def _collect_news(
        self,
        item: str,
        country: str,
        errors: list[str],
        sources: list[str],
    ) -> list[dict[str, Any]]:
        """Collect news signals from GDELT (free) and NewsData."""
        signals: list[dict[str, Any]] = []

        # GDELT (free, no key)
        try:
            from upstream_alert.sources import gdelt

            query = f"supply chain {item}"
            articles = gdelt.search_articles(query, timespan="7d")
            signals.extend(s.model_dump() for s in gdelt.to_signals(articles))
            if articles:
                sources.append("gdelt")
        except Exception as e:
            errors.append(f"GDELT: {e}")

        # NewsData
        if self._newsdata_key:
            try:
                from upstream_alert.sources import newsdata

                articles = newsdata.search_supply_chain(
                    self._newsdata_key, country=country, item_name=item,
                )
                signals.extend(
                    s.model_dump() for s in newsdata.to_signals(articles)
                )
                if articles:
                    sources.append("newsdata")
            except Exception as e:
                errors.append(f"NewsData: {e}")

        return signals

    def _collect_freight(
        self, errors: list[str], sources: list[str],
    ) -> FreightSignal | None:
        """Collect freight index from FBX."""
        try:
            from upstream_alert.sources import fbx

            signal = fbx.fetch_global_index(self._fbx_key)
            # Only count as real source if not using mock data
            if signal.source != "mock":
                sources.append("fbx")
            return signal
        except Exception as e:
            errors.append(f"FBX: {e}")
            return None

    def _collect_trade(
        self,
        country: str,
        item: str,
        errors: list[str],
        sources: list[str],
    ) -> list[dict[str, Any]]:
        """Collect trade data from Comtrade."""
        if not self._comtrade_key:
            return []
        try:
            from upstream_alert.sources import comtrade

            # Try to guess HS code from item name
            hs_code = _guess_hs_code(item)
            records = comtrade.fetch_trade_data(
                self._comtrade_key,
                country_code=country,
                cmd_code=hs_code,
            )
            if records:
                sources.append("comtrade")
            return records
        except Exception as e:
            errors.append(f"Comtrade: {e}")
            return []

    # ── Scoring ──

    def _calculate_score(
        self,
        price_signals: list[dict[str, Any]],
        news_signals: list[dict[str, Any]],
        freight: FreightSignal | None,
        trade_data: list[dict[str, Any]],
    ) -> int:
        """Calculate composite risk score (0-100).

        Weights:
        - CPI pressure: 30%
        - News sentiment: 30%
        - Freight trends: 20%
        - Trade volume changes: 20%
        """
        score = 0.0

        # CPI component (30 pts max)
        if price_signals:
            cpi_change = price_signals[0].get("yoy_change", 0)
            if cpi_change > 5:
                score += 30
            elif cpi_change > 3:
                score += 20
            elif cpi_change > 2:
                score += 10
            elif cpi_change < 0:
                score += 5  # deflation is also a risk

        # News sentiment (30 pts max)
        if news_signals:
            negative = sum(
                1 for n in news_signals if n.get("sentiment", 0) < -0.2
            )
            ratio = negative / len(news_signals) if news_signals else 0
            score += min(30, ratio * 60)

        # Freight (20 pts max)
        if freight and freight.source != "mock":
            if freight.change_pct > 10:
                score += 20
            elif freight.change_pct > 5:
                score += 15
            elif freight.change_pct > 0:
                score += 5

        # Trade volume (20 pts max)
        if not trade_data:
            score += 10  # uncertainty penalty

        return min(100, max(0, int(score)))


# ── Convenience function ──

def check_risk(item: str, country: str = "TW", **kwargs: Any) -> RiskResult:
    """One-liner convenience for quick risk checks.

    Usage:
        from upstream_alert import check_risk
        result = check_risk("咖啡豆", country="TW")
    """
    engine = RiskEngine(**kwargs)
    return engine.check(item, country)


# ── Helpers ──

_ITEM_HS_MAP: dict[str, str] = {
    "咖啡": "0901", "coffee": "0901",
    "茶": "0902", "tea": "0902",
    "米": "1006", "rice": "1006",
    "小麥": "1001", "wheat": "1001",
    "黃金": "7108", "gold": "7108",
    "銅": "7403", "copper": "7403",
    "鋼鐵": "7206", "steel": "7206", "iron": "7206",
    "電腦": "8471", "computer": "8471",
    "半導體": "8542", "semiconductor": "8542", "chip": "8542",
    "汽車": "8703", "car": "8703", "automobile": "8703",
}


def _guess_hs_code(item: str) -> str:
    """Try to map an item name to an HS code."""
    item_lower = item.lower().strip()
    for keyword, code in _ITEM_HS_MAP.items():
        if keyword in item_lower:
            return code
    return "0901"  # default: coffee

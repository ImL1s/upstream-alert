"""Gemini AI analysis wrapper.

Uses google-genai to generate AI-powered risk summaries.
Requires a Gemini API key (free tier: 15 RPM).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def analyze_risk(
    item: str,
    country: str,
    price_signals: list[dict[str, Any]],
    news_signals: list[dict[str, Any]],
    market_pulse: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> str:
    """Generate an AI-powered risk analysis summary.

    Uses Gemini to synthesize price, news, and market data
    into a human-readable risk assessment.

    Falls back to a template-based summary if no API key or on error.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return _template_summary(item, country, price_signals, news_signals)

    try:
        from google import genai

        client = genai.Client(api_key=key)
        prompt = _build_prompt(item, country, price_signals, news_signals, market_pulse)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text or _template_summary(
            item, country, price_signals, news_signals,
        )
    except Exception as e:
        logger.warning("Gemini analysis failed: %s", e)
        return _template_summary(item, country, price_signals, news_signals)


def _build_prompt(
    item: str,
    country: str,
    price_signals: list[dict[str, Any]],
    news_signals: list[dict[str, Any]],
    market_pulse: dict[str, Any] | None,
) -> str:
    """Build the analysis prompt."""
    price_txt = ""
    if price_signals:
        for s in price_signals[:5]:
            price_txt += f"- {s.get('category','?')}: {s.get('yoy_change',0):.1f}% YoY ({s.get('period','')})\n"

    news_txt = ""
    if news_signals:
        for n in news_signals[:5]:
            news_txt += f"- {n.get('title','?')}\n"

    pulse_txt = ""
    if market_pulse:
        pulse_txt = f"""
Freight Index: {market_pulse.get('freight', {}).get('index', 'N/A')}
CPI Change: {market_pulse.get('cpi_change', 'N/A')}%
PMI: {market_pulse.get('pmi', 'N/A')}"""

    return f"""You are a supply chain risk analyst. Analyze the following data
and provide a brief risk assessment for "{item}" in {country}.

=== PRICE SIGNALS ===
{price_txt or 'No data available'}

=== RECENT NEWS ===
{news_txt or 'No news found'}

=== MARKET PULSE ===
{pulse_txt or 'No market data'}

Provide a concise analysis (2-3 paragraphs) covering:
1. Current risk level and key risk factors
2. Supply chain implications
3. Recommended actions for importers/business owners

Be factual. If data is limited, say so. Output in the same language as the item name."""


def _template_summary(
    item: str,
    country: str,
    price_signals: list[dict[str, Any]],
    news_signals: list[dict[str, Any]],
) -> str:
    """Template-based fallback when AI is unavailable."""
    parts = [f"Risk assessment for {item} ({country}):"]

    if price_signals:
        latest = price_signals[0]
        yoy = latest.get("yoy_change", 0)
        if yoy > 3:
            parts.append(f"⚠️ Price pressure: CPI up {yoy:.1f}% YoY")
        elif yoy < 0:
            parts.append(f"✅ Deflationary trend: CPI {yoy:.1f}% YoY")
        else:
            parts.append(f"Price stable: CPI {yoy:.1f}% YoY")

    if news_signals:
        negative = [n for n in news_signals if n.get("sentiment", 0) < -0.2]
        if negative:
            parts.append(
                f"📰 {len(negative)} concerning news article(s) detected"
            )
        else:
            parts.append("📰 No major negative news signals")

    return "\n".join(parts)

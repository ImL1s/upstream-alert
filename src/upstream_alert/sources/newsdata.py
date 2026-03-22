"""NewsData.io adapter.

Fetches international news articles with sentiment.
Free tier: 200 credits/day (1 request = 1 credit).
https://newsdata.io
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from upstream_alert.models import NewsSignal

logger = logging.getLogger(__name__)

_API = "https://newsdata.io/api/1/latest"


def search_news(
    api_key: str,
    query: str = "supply chain",
    country: str | None = None,
    category: str = "business",
    language: str = "en",
    max_results: int = 10,
    timeout: int = 15,
) -> list[dict[str, Any]]:
    """Search for news articles matching a query.

    Args:
        api_key: NewsData.io API key
        query: Search keywords
        country: ISO2 country code (None = global)
        category: News category
        language: Language code
        max_results: Max articles to return
        timeout: Request timeout

    Returns:
        Raw article dicts from NewsData API.
    """
    params: dict[str, Any] = {
        "apikey": api_key,
        "q": query,
        "category": category,
        "language": language,
        "size": min(max_results, 50),
    }
    if country:
        params["country"] = country.lower()

    try:
        resp = requests.get(_API, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except (requests.RequestException, ValueError) as e:
        logger.warning("NewsData API error: %s", e)
        return []


def search_supply_chain(
    api_key: str,
    country: str | None = None,
    item_name: str | None = None,
) -> list[dict[str, Any]]:
    """Convenience: search supply chain news for a specific item."""
    parts = ["supply chain"]
    if item_name:
        parts.append(item_name)
    return search_news(api_key, query=" ".join(parts), country=country)


def to_signals(articles: list[dict[str, Any]]) -> list[NewsSignal]:
    """Convert raw NewsData articles to NewsSignal models."""
    signals = []
    for art in articles:
        sentiment_raw = art.get("sentiment")
        if isinstance(sentiment_raw, str):
            sentiment_map = {"positive": 0.5, "negative": -0.5, "neutral": 0.0}
            sentiment = sentiment_map.get(sentiment_raw, 0.0)
        elif isinstance(sentiment_raw, (int, float)):
            sentiment = float(sentiment_raw)
        else:
            sentiment = 0.0

        signals.append(NewsSignal(
            title=art.get("title", ""),
            url=art.get("link", ""),
            source_name=art.get("source_name", art.get("source_id", "")),
            published=art.get("pubDate", ""),
            sentiment=sentiment,
        ))
    return signals

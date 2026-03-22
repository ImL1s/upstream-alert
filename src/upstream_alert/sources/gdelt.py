"""GDELT DOC API adapter.

Fetches global news articles from the GDELT Project.
Free, no API key required. Rate limits are strict but undocumented.
https://api.gdeltproject.org/api/v2/doc/doc
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from upstream_alert.models import NewsSignal

logger = logging.getLogger(__name__)

_API = "https://api.gdeltproject.org/api/v2/doc/doc"


def search_articles(
    query: str,
    timespan: str = "7d",
    max_records: int = 30,
    sourcelang: str = "english",
    timeout: int = 10,
) -> list[dict[str, Any]]:
    """Search GDELT for articles matching a query.

    Returns raw article dicts with {url, title, seendate, domain, tone, ...}.
    """
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "timespan": timespan,
        "maxrecords": max_records,
        "sourcelang": sourcelang,
    }
    try:
        resp = requests.get(_API, params=params, timeout=timeout)
        if resp.status_code == 429:
            logger.warning("GDELT rate limited (429)")
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("articles", [])
    except (requests.RequestException, ValueError) as e:
        logger.warning("GDELT API error: %s", e)
        return []


def to_signals(articles: list[dict[str, Any]]) -> list[NewsSignal]:
    """Convert raw GDELT articles to NewsSignal models."""
    signals = []
    for art in articles:
        tone_str = art.get("tone", "0")
        try:
            tone = float(str(tone_str).split(",")[0]) if tone_str else 0.0
        except (ValueError, IndexError):
            tone = 0.0

        signals.append(NewsSignal(
            title=art.get("title", ""),
            url=art.get("url", ""),
            source_name=art.get("domain", ""),
            published=art.get("seendate", ""),
            sentiment=max(-1.0, min(1.0, tone / 10)),  # normalize
        ))
    return signals

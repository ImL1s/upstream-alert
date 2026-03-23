"""Yahoo Finance commodity futures adapter.

Fetches daily closing prices for major commodity futures via yfinance.
This is a non-official API — use as an enhancement layer (fallback to FRED if unavailable).

Yahoo Finance is completely free and requires no API key.
Supported tickers: HG=F (Copper), ALI=F (Aluminum), ZS=F (Soybean),
                   CT=F (Cotton), KC=F (Coffee).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta, timezone
from typing import Any

from upstream_alert.models import PriceSignal

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10

# item keyword → Yahoo Finance ticker
# Supports both English and CJK (zh-TW) keywords
TICKER_MAP: dict[str, str] = {
    "copper": "HG=F",
    "銅": "HG=F",
    "aluminum": "ALI=F",
    "鋁": "ALI=F",
    "soybean": "ZS=F",
    "黃豆": "ZS=F",
    "cotton": "CT=F",
    "棉": "CT=F",
    "coffee": "KC=F",
    "咖啡": "KC=F",
}


def _match_ticker(item: str) -> str | None:
    """Try to match an item name to a Yahoo Finance ticker."""
    item_lower = item.lower()
    for keyword, ticker in TICKER_MAP.items():
        if keyword in item_lower:
            return ticker
    return None


def fetch_daily_prices(
    item: str,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Fetch daily commodity futures prices.

    Args:
        item: Item name or keyword (e.g. "copper", "咖啡豆", "黃豆")
        days: Number of trading days to retrieve

    Returns:
        [{date: "2026-03-16", value: 5.47, source: "yahoo", ticker: "HG=F"}, ...]
        Sorted ascending by date. Returns empty list on any error.
    """
    ticker = _match_ticker(item)
    if not ticker:
        return []

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_fetch_impl, ticker, days)
            return future.result(timeout=_TIMEOUT_SECONDS)
    except FuturesTimeout:
        logger.warning("Yahoo Finance timeout (%ds) for %s", _TIMEOUT_SECONDS, ticker)
        return []
    except Exception as e:
        logger.warning("Yahoo Finance failed for %s: %s", ticker, e)
        return []


def _fetch_impl(ticker: str, days: int) -> list[dict[str, Any]]:
    """Actual yfinance fetch (runs in a thread for timeout safety)."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — Yahoo Finance source disabled")
        return []

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 5)

    t = yf.Ticker(ticker)
    hist = t.history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
    )

    if hist.empty:
        logger.warning("Yahoo Finance: empty data for %s", ticker)
        return []

    records = []
    for idx, row in hist.iterrows():
        close_val = row.get("Close")
        if close_val is not None and not (
            isinstance(close_val, float) and close_val != close_val
        ):
            records.append({
                "date": idx.strftime("%Y-%m-%d"),
                "value": round(float(close_val), 2),
                "source": "yahoo",
                "ticker": ticker,
            })

    return records[-days:] if len(records) > days else records


def to_signals(records: list[dict[str, Any]]) -> list[PriceSignal]:
    """Convert raw Yahoo Finance records to PriceSignal models."""
    return [
        PriceSignal(
            source="yahoo",
            period=r["date"],
            category="commodity_futures",
            index_value=r["value"],
            yoy_change=0.0,  # daily data, no YoY available
        )
        for r in records
    ]


def supported_keywords() -> list[str]:
    """Return supported item keywords."""
    return list(TICKER_MAP.keys())

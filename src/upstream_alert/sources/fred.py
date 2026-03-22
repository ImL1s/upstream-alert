"""FRED (Federal Reserve Economic Data) adapter.

Fetches CPI/PPI from the FRED API.
Free API key: https://fred.stlouisfed.org/docs/api/api_key.html (120 req/min)
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from upstream_alert.models import PriceSignal

logger = logging.getLogger(__name__)

_API = "https://api.stlouisfed.org/fred/series/observations"

# series_id where value is already YoY %, not an index
_PCT_CHANGE_SERIES: set[str] = {
    "TWNPCPIPCPPPT",
    "TWNPIEAMP01GYM",
}

# Convenient presets per country
COUNTRY_SERIES: dict[str, dict[str, str]] = {
    "TW": {"cpi": "TWNPCPIPCPPPT", "ppi": "TWNPIEAMP01GYM"},
    "JP": {"cpi": "JPNCPIALLMINMEI"},
    "US": {"cpi": "CPIAUCSL"},
    "DE": {"cpi": "DEUCPIALLMINMEI"},
    "KR": {"cpi": "KORCPIALLMINMEI"},
    "CN": {"cpi": "CHNCPIALLMINMEI"},
    "GB": {"cpi": "GBRCPIALLMINMEI"},
}


def fetch_observations(
    api_key: str,
    series_id: str,
    limit: int = 13,
    timeout: int = 15,
) -> list[dict[str, Any]]:
    """Fetch raw observations from FRED API.

    Returns list of {date, value, source, series_id}.
    """
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    try:
        resp = requests.get(_API, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("FRED API error for %s: %s", series_id, e)
        return []

    records = []
    for obs in data.get("observations", []):
        val = obs.get("value", ".")
        if val == ".":
            continue
        try:
            records.append({
                "date": obs.get("date", ""),
                "value": float(val),
                "source": "fred",
                "series_id": series_id,
            })
        except (ValueError, TypeError):
            continue
    return records


def get_latest_cpi_change(api_key: str, series_id: str) -> float:
    """Get the latest CPI YoY % change for a given FRED series."""
    if series_id in _PCT_CHANGE_SERIES:
        records = fetch_observations(api_key, series_id, limit=1)
        return records[0]["value"] if records else 0.0

    # Index type: need current + 12-month-ago
    records = fetch_observations(api_key, series_id, limit=13)
    if len(records) >= 13:
        current = records[0]["value"]
        prev = records[12]["value"]
        if prev > 0:
            return round(((current - prev) / prev) * 100, 2)
    return 0.0


def to_signals(records: list[dict[str, Any]]) -> list[PriceSignal]:
    """Convert raw observations to PriceSignal models."""
    signals = []
    for i, rec in enumerate(records):
        value = rec.get("value", 0)
        sid = rec.get("series_id", "")

        if sid in _PCT_CHANGE_SERIES:
            yoy = value
        else:
            yoy = 0.0
            prev_idx = i + 12
            if prev_idx < len(records):
                prev = records[prev_idx].get("value", 0)
                if prev and prev > 0:
                    yoy = round(((value - prev) / prev) * 100, 2)

        signals.append(PriceSignal(
            source="fred",
            period=rec.get("date", ""),
            category="CPI",
            index_value=value,
            yoy_change=yoy,
        ))
    return signals

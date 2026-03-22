"""World Bank API v2 adapter.

Fetches CPI, GDP growth, trade-to-GDP from the World Bank.
Free, no API key required.
Note: Taiwan (TWN) is NOT in the World Bank dataset.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from upstream_alert.models import PriceSignal

logger = logging.getLogger(__name__)

_API = "https://api.worldbank.org/v2/country"

INDICATORS: dict[str, str] = {
    "cpi": "FP.CPI.TOTL.ZG",
    "gdp_growth": "NY.GDP.MKTP.KD.ZG",
    "trade_pct_gdp": "NE.TRD.GNFS.ZS",
}

_ISO2_TO_ISO3: dict[str, str] = {
    "TW": "TWN", "JP": "JPN", "US": "USA", "DE": "DEU",
    "KR": "KOR", "CN": "CHN", "GB": "GBR", "FR": "FRA",
    "IN": "IND", "BR": "BRA", "VN": "VNM", "TH": "THA",
}


def fetch_indicator(
    country_code: str = "JP",
    indicator_key: str = "cpi",
    limit: int = 10,
    timeout: int = 15,
) -> list[dict[str, Any]]:
    """Fetch a World Bank indicator for a country.

    Returns:
        [{date, value, country, indicator, source}, ...]
        Empty list if country not in dataset (e.g. Taiwan).
    """
    iso3 = _ISO2_TO_ISO3.get(country_code.upper(), country_code.upper())
    indicator = INDICATORS.get(indicator_key, indicator_key)

    url = f"{_API}/{iso3}/indicator/{indicator}"
    params = {
        "format": "json",
        "per_page": limit,
        "mrv": limit,  # most recent values
    }

    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("World Bank API error: %s", e)
        return []

    if not isinstance(data, list) or len(data) < 2:
        return []

    records = []
    for entry in data[1] or []:
        value = entry.get("value")
        if value is None:
            continue
        records.append({
            "date": entry.get("date", ""),
            "value": round(float(value), 2),
            "country": iso3,
            "indicator": indicator,
            "source": "worldbank",
        })
    return records


def get_latest_cpi(country_code: str = "JP") -> float:
    """Get latest CPI YoY % change. Returns 0.0 if unavailable."""
    records = fetch_indicator(country_code, "cpi", limit=1)
    return records[0]["value"] if records else 0.0


def to_signals(records: list[dict[str, Any]]) -> list[PriceSignal]:
    """Convert raw World Bank data to PriceSignal models."""
    return [
        PriceSignal(
            source="worldbank",
            period=r.get("date", ""),
            category="CPI",
            index_value=r.get("value", 0),
            yoy_change=r.get("value", 0),
        )
        for r in records
    ]

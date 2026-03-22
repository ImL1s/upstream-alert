"""UN Comtrade API v2 adapter.

Fetches international trade data (import/export volumes).
Free API key: https://comtradeplus.un.org/ (500 calls/day, 100/hr)
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from upstream_alert.models import TradeSignal

logger = logging.getLogger(__name__)

_API = "https://comtradeapi.un.org/data/v1/get"

# ISO2 → ISO3 mapping
_ISO2_TO_ISO3: dict[str, str] = {
    "TW": "TWN", "JP": "JPN", "US": "USA", "DE": "DEU",
    "KR": "KOR", "CN": "CHN", "GB": "GBR", "FR": "FRA",
    "VN": "VNM", "TH": "THA", "IN": "IND", "BR": "BRA",
}

# Comtrade M49 reporter codes
_REPORTER_CODES: dict[str, str] = {
    "TWN": "490", "JPN": "392", "USA": "842", "DEU": "276",
    "KOR": "410", "CHN": "156", "GBR": "826", "FRA": "250",
    "VNM": "704", "THA": "764", "IND": "356", "BRA": "076",
}

# Common HS codes
HS_CODES: dict[str, str] = {
    "coffee": "0901",
    "tea": "0902",
    "rice": "1006",
    "wheat": "1001",
    "gold": "7108",
    "copper": "7403",
    "iron_steel": "7206",
    "computers": "8471",
    "semiconductors": "8542",
    "automobiles": "8703",
}


def fetch_trade_data(
    api_key: str,
    country_code: str = "JP",
    cmd_code: str = "0901",
    flow_code: str = "M,X",
    limit: int = 50,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Query trade data for a country + commodity.

    Args:
        api_key: Comtrade subscription key
        country_code: ISO2 country code
        cmd_code: HS code for the commodity
        flow_code: M=import, X=export, or "M,X" for both
        limit: Max records to return
        timeout: Request timeout in seconds

    Returns:
        List of trade data dicts.
    """
    iso3 = _ISO2_TO_ISO3.get(country_code.upper(), country_code.upper())
    reporter = _REPORTER_CODES.get(iso3)
    if not reporter:
        logger.warning("Comtrade: no reporter code for %s", iso3)
        return []

    url = f"{_API}/C/A/HS"
    params = {
        "reporterCode": reporter,
        "cmdCode": cmd_code,
        "flowCode": flow_code,
        "partnerCode": "0",  # World
        "period": "recent",
        "maxRecords": limit,
    }
    headers = {"Ocp-Apim-Subscription-Key": api_key}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except (requests.RequestException, ValueError) as e:
        logger.warning("Comtrade API error: %s", e)
        return []


def to_signals(records: list[dict[str, Any]]) -> list[TradeSignal]:
    """Convert raw Comtrade data to TradeSignal models."""
    signals = []
    for rec in records:
        signals.append(TradeSignal(
            reporter=rec.get("reporterISO", ""),
            partner=rec.get("partnerDesc", "World"),
            flow="M" if rec.get("flowCode") == "M" else "X",
            commodity=rec.get("cmdDesc", ""),
            hs_code=str(rec.get("cmdCode", "")),
            value_usd=rec.get("primaryValue", 0) or 0,
            quantity=rec.get("qty", 0) or 0,
            period=str(rec.get("period", "")),
        ))
    return signals

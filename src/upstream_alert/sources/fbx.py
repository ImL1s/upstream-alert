"""Freightos FBX (Baltic Index) adapter.

Fetches global container shipping freight rates.
Note: FBX API requires a paid subscription ($119/mo).
Provides mock fallback data for development/demo.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from upstream_alert.models import FreightSignal

logger = logging.getLogger(__name__)

_API = "https://fbx.freightos.com/api/v1"


def fetch_global_index(
    api_key: str | None = None,
    timeout: int = 30,
) -> FreightSignal:
    """Fetch FBX global composite index.

    Falls back to mock data if no API key is configured.
    """
    if not api_key:
        return _mock_index()

    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(
            f"{_API}/index/global", headers=headers, timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return FreightSignal(
            index=data.get("index", 0),
            change_pct=data.get("change_pct", 0),
            date=data.get("date", ""),
            source="fbx",
        )
    except requests.RequestException as e:
        logger.warning("FBX API error: %s", e)
        return _mock_index()


def _mock_index() -> FreightSignal:
    """Mock data for development / demo use."""
    return FreightSignal(
        index=2150.0,
        change_pct=-1.5,
        date="mock",
        source="mock",
    )

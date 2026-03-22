"""upstream-alert — Supply chain risk monitoring engine.

Usage:
    from upstream_alert import check_risk, RiskEngine

    result = check_risk("咖啡豆", country="TW")
    print(result.score, result.level, result.ai_summary)
"""

from upstream_alert.engine import RiskEngine, check_risk
from upstream_alert.models import RiskLevel, RiskResult, PriceSignal, NewsSignal

__version__ = "0.1.0"
__all__ = [
    "RiskEngine",
    "check_risk",
    "RiskLevel",
    "RiskResult",
    "PriceSignal",
    "NewsSignal",
]

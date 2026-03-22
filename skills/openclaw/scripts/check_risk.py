#!/usr/bin/env python3
"""OpenClaw skill script: check supply chain risk.

Protocol: JSON output to stdout, exit 0 on success, 1 on error.
Zero external dependencies beyond upstream-alert itself.

Usage (called by OpenClaw):
    python scripts/check_risk.py "咖啡豆" TW
"""

import json
import sys

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: check_risk.py <item> [country]"}))
        sys.exit(1)

    item = sys.argv[1]
    country = sys.argv[2] if len(sys.argv) > 2 else "TW"

    try:
        from upstream_alert.engine import RiskEngine

        engine = RiskEngine()
        result = engine.check(item, country)

        output = {
            "status": "ok",
            "item": result.item,
            "country": result.country,
            "score": result.score,
            "level": result.level.value,
            "brief": result.to_brief(),
            "ai_summary": result.ai_summary,
            "sources_used": result.sources_used,
            "errors": result.errors,
        }
        if result.market_pulse:
            output["market_pulse"] = {
                "cpi_change": result.market_pulse.cpi_change,
                "freight_index": result.market_pulse.freight.index if result.market_pulse.freight else None,
                "freight_change": result.market_pulse.freight.change_pct if result.market_pulse.freight else None,
            }

        print(json.dumps(output, ensure_ascii=False, indent=2))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

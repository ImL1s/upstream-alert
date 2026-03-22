---
name: upstream-alert
description: >
  Supply chain risk monitoring — check CPI, freight rates, trade data, and
  global news to assess risk for any commodity. Uses FRED, GDELT, UN Comtrade,
  World Bank, NewsData, and Gemini AI. Bring your own API keys (free tiers available).
  Trigger keywords: supply chain, risk, CPI, freight, import, export, trade, commodity,
  price trend, supply disruption, shipping cost, inflation, PMI, economic indicator.
homepage: https://github.com/ImL1s/upstream-alert
metadata:
  openclaw:
    emoji: 🔍
    primaryEnv: GEMINI_API_KEY
    requires:
      bins:
        - python3
      env:
        - GEMINI_API_KEY
    install:
      - id: "upstream-alert-pip"
        kind: "pip"
        package: "upstream-alert"
        bins: ["upstream-alert"]
        label: "Install upstream-alert (pip)"
---

# upstream-alert — Supply Chain Risk Monitor

Supply chain risk monitoring engine for AI agents. Queries 6+ data sources to produce a risk score (0-100) with AI-generated analysis.

## Prerequisites

- Python 3.10+
- `pip install upstream-alert`
- Set API keys as environment variables (see below)

## Environment Variables

| Source | Env Var | Free Tier |
|--------|---------|-----------|
| Gemini AI (Analysis) | `GEMINI_API_KEY` | 15 RPM free |
| FRED (CPI/PPI) | `FRED_API_KEY` | 120 req/min |
| UN Comtrade (Trade) | `COMTRADE_API_KEY` | 500 req/day |
| NewsData.io (News) | `NEWSDATA_API_KEY` | 200 req/day |
| Freightos FBX (Freight) | `FBX_API_KEY` | Paid ($119/mo) |
| GDELT (News) | None needed | Unlimited |
| World Bank (Indicators) | None needed | Unlimited |

> 💡 Start with just `GEMINI_API_KEY`. GDELT and World Bank work without any key.

## Usage

### Quick risk check (CLI)
```bash
upstream-alert check "咖啡豆" --country TW
```

### JSON output
```bash
upstream-alert check "semiconductor" --country US -j
```

### Market pulse
```bash
upstream-alert pulse --country JP
```

### Show configured sources
```bash
upstream-alert sources
```

### Python API
```python
from upstream_alert import check_risk

result = check_risk("coffee", country="US")
print(result.score, result.level, result.ai_summary)
```

### OpenClaw script
```bash
python3 {baseDir}/scripts/check_risk.py "咖啡豆" TW
```

## Script Protocol

Scripts in `{baseDir}/scripts/` output JSON to stdout with exit code 0 on success, 1 on error.

### {baseDir}/scripts/check_risk.py
```
Input:  python3 {baseDir}/scripts/check_risk.py <item> [country_code]
Output: JSON with status, score, level, ai_summary, market_pulse, sources_used
```

## When to Use This Skill

Use when the user asks about:
- Supply chain risks for a product or commodity
- Price trends (CPI, PPI, inflation)
- Shipping / freight cost trends
- Trade data for imports/exports
- Economic indicators for a country
- News analysis for supply chain disruptions

## Trigger Keywords
supply chain, risk, CPI, freight, import, export, trade, commodity, price trend,
supply disruption, shipping cost, inflation, PMI, economic indicator, 供應鏈, 風險

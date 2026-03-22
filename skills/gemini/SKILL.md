---
name: upstream-alert
description: >
  Supply chain risk monitoring — check CPI, freight rates, trade data, and
  global news to assess risk for any commodity. Uses FRED, GDELT, UN Comtrade,
  World Bank, NewsData, and Gemini AI. Bring your own API keys (free tiers available).
  Trigger keywords: supply chain, risk, CPI, freight, import, export, trade, commodity,
  price trend, supply disruption, shipping cost, inflation, economic indicator.
---

# upstream-alert — Supply Chain Risk Monitor

## Installation

```bash
pip install upstream-alert
```

## Environment Variables

Set API keys before use. Only `GEMINI_API_KEY` is required; GDELT and World Bank work without keys.

```bash
# Required
export GEMINI_API_KEY="your_gemini_key"

# Optional (enables more data sources)
export FRED_API_KEY="your_fred_key"
export COMTRADE_API_KEY="your_comtrade_key"
export NEWSDATA_API_KEY="your_newsdata_key"
export FBX_API_KEY="your_fbx_key"
```

## Usage

### CLI Commands

```bash
# Risk check
upstream-alert check "咖啡豆" --country TW

# JSON output
upstream-alert check "semiconductor" --country US -j

# Market pulse
upstream-alert pulse --country JP

# Show data sources
upstream-alert sources
```

### Python API

```python
from upstream_alert import check_risk

result = check_risk("coffee", country="US")
print(result.score, result.level, result.ai_summary)
```

## When to Use

Use when the user asks about:
- Supply chain risks for a product or commodity
- Price trends (CPI, PPI, inflation data)
- Shipping / freight cost trends
- Trade data for imports/exports
- Economic indicators for a country
- News analysis related to supply chain disruptions

## Trigger Keywords
supply chain, risk, CPI, freight, import, export, trade, commodity, price trend,
supply disruption, shipping cost, inflation, PMI, economic indicator

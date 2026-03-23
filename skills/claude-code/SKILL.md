---
name: upstream-alert
description: >
  Supply chain risk monitoring — check CPI, commodity prices, freight rates,
  trade data, and global news to assess risk for any commodity. Uses Yahoo Finance,
  FRED, Commodities-API, UN Comtrade, World Bank, NewsData, and Gemini AI.
  Covers 20 items across 8 categories (construction, energy, food, electronics,
  packaging, chemicals, textiles, electrical). Bring your own API keys (free tiers available).
  Trigger keywords: supply chain, risk, CPI, freight, import, export, trade, commodity,
  price trend, supply disruption, shipping cost, inflation, economic indicator.
dependencies:
  - upstream-alert
---

# upstream-alert — Supply Chain Risk Monitor

## Installation

```bash
pip install upstream-alert
```

## Environment Variables

Set API keys before use. Only `GEMINI_API_KEY` is required; World Bank and Yahoo Finance work without keys.

```bash
# Required
export GEMINI_API_KEY="your_gemini_key"

# Optional (enables more data sources)
# Yahoo Finance: no key needed — daily commodity futures (copper, aluminum, soybean, cotton, coffee)
# Install with: pip install upstream-alert[yahoo]
export FRED_API_KEY="your_fred_key"                    # https://fred.stlouisfed.org/docs/api/api_key.html
export COMMODITIES_API_KEY="your_commodities_key"      # https://commodities-api.com/ (100 req/month free)
export COMTRADE_API_KEY="your_comtrade_key"            # https://comtradeplus.un.org/
export NEWSDATA_API_KEY="your_newsdata_key"            # https://newsdata.io/
export FBX_API_KEY="your_fbx_key"                      # Paid: $119/mo
```

## Supported Item Categories (20 items)

| Category | Examples |
|----------|----------|
| 建材 (Construction) | 鋼筋, 合板, 水泥 |
| 機電 (Electrical) | 電線電纜 |
| 能源 (Energy) | 柴油, 汽油, 天然氣 |
| 食品原料 (Food) | 黃豆, 麵粉, 棕櫚油, 砂糖, 咖啡豆 |
| 電子零件 (Electronics) | 晶片 MCU, 被動元件 |
| 包材 (Packaging) | 瓦楞紙箱, PE 膜 |
| 化工 (Chemicals) | 塑膠粒, 工業酒精 |
| 紡織 (Textiles) | 棉紗, 滌綸纖維 |

## Usage

### CLI Commands

```bash
# Risk check (human readable)
upstream-alert check "咖啡豆" --country TW

# Risk check (JSON output)
upstream-alert check "semiconductor" --country US -j

# Market pulse
upstream-alert pulse --country JP

# Show configured data sources
upstream-alert sources
```

### Python API

```python
from upstream_alert import check_risk, RiskEngine

# One-liner
result = check_risk("coffee", country="US")
print(result.score)       # 45
print(result.level)       # RiskLevel.MEDIUM
print(result.ai_summary)  # AI-generated analysis

# Full control
engine = RiskEngine(fred_key="...", gemini_key="...")
result = engine.check("半導體", country="TW")
```

## Output Format (JSON)

```json
{
  "item": "coffee",
  "country": "US",
  "score": 45,
  "level": "medium",
  "ai_summary": "Risk assessment for coffee (US): ...",
  "sources_used": ["fred", "commodities_api", "newsdata"],
  "market_pulse": {
    "cpi_change": 2.1,
    "commodity_price": 5.62,
    "freight": { "index": 2150.0, "change_pct": -1.5 }
  }
}
```

## When to Use

Use when the user asks about:
- Supply chain risks for a product or commodity
- Real-time commodity prices (metals, energy, food, textiles)
- Price trends (CPI, PPI, inflation data)
- Shipping / freight cost trends
- Trade data for imports/exports
- Economic indicators for a country
- News analysis related to supply chain disruptions

## Trigger Keywords
supply chain, risk, CPI, freight, import, export, trade, commodity, price trend,
supply disruption, shipping cost, inflation, PMI, economic indicator, commodity price

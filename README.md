# 🔍 upstream-alert

**Supply chain risk monitoring engine** — CLI tool + AI Agent Skill (OpenClaw / Claude Code / Gemini)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/upstream-alert.svg)](https://pypi.org/project/upstream-alert/)

Monitor supply chain risks by aggregating data from **6 global sources**, scoring risk (0-100), and generating AI-powered analysis.

## ⚡ Quick Start

```bash
pip install upstream-alert

# Set at least one key (Gemini for AI analysis)
export GEMINI_API_KEY="your_key"

# Check risk
upstream-alert check "咖啡豆" --country TW
```

Output:
```
🔍 Checking risk for '咖啡豆' (TW)...

🟡 咖啡豆 (TW) — Score: 45/100 [MEDIUM]

📊 Analysis:
  Current CPI pressure is moderate at 2.1% YoY...

📈 Market Pulse:
  🚢 Freight: 2150 (↓1.5%)
  📊 CPI: +2.1% YoY

📡 Sources: fred, gdelt, fbx
```

## 📡 Data Sources

| Source | Key | Free Tier | Data |
|--------|-----|-----------|------|
| **FRED** | `FRED_API_KEY` | 120 req/min | CPI, PPI |
| **UN Comtrade** | `COMTRADE_API_KEY` | 500 req/day | Trade volumes |
| **NewsData.io** | `NEWSDATA_API_KEY` | 200 req/day | News + sentiment |
| **Gemini AI** | `GEMINI_API_KEY` | 15 RPM | AI analysis |
| **GDELT** | None ✅ | Unlimited | Global news |
| **World Bank** | None ✅ | Unlimited | Economic indicators |
| **Freightos FBX** | `FBX_API_KEY` | Paid ($119/mo) | Freight rates |

> 💡 GDELT and World Bank work without any key. Start with just `GEMINI_API_KEY` for a basic setup.

## 🛠 Usage

### CLI

```bash
# Risk check (human-readable)
upstream-alert check "semiconductor" --country US

# Risk check (JSON)
upstream-alert check "rice" --country JP -j

# Market pulse
upstream-alert pulse --country TW

# Show configured sources
upstream-alert sources
```

### Python API

```python
from upstream_alert import check_risk, RiskEngine

# One-liner
result = check_risk("coffee", country="US")
print(result.score)       # 45
print(result.level)       # RiskLevel.MEDIUM
print(result.ai_summary)  # "Current CPI pressure..."

# Full control
engine = RiskEngine(
    fred_key="your_key",
    gemini_key="your_key",
)
result = engine.check("半導體", country="TW")
```

### AI Agent Skill

Works with **OpenClaw**, **Claude Code**, and **Gemini CLI**:

```
User: What's the supply chain risk for coffee beans in Taiwan?

Agent: [uses upstream-alert skill]
       🟡 咖啡豆 (TW) — Score: 45/100 [MEDIUM]
       
       📊 Analysis:
       CPI pressure is moderate. Global freight rates are
       trending down (-1.5%), which is favorable for importers...
```

## 🔌 Install as AI Skill

### OpenClaw
```bash
claw skill install upstream-alert
```

### Claude Code
```bash
# Copy to skills directory
cp -r skills/claude-code ~/.claude/skills/upstream-alert
pip install upstream-alert
```

### Gemini CLI
```bash
cp -r skills/gemini ~/.gemini/antigravity/skills/upstream-alert
pip install upstream-alert
```

## 📊 How Risk Scoring Works

The engine calculates a composite score (0-100) from four components:

| Factor | Weight | Signals |
|--------|--------|---------|
| CPI pressure | 30% | YoY inflation rate |
| News sentiment | 30% | Negative news ratio |
| Freight trends | 20% | FBX index change |
| Trade uncertainty | 20% | Volume data availability |

**Risk Levels:**
- 🟢 **Low** (0-39): Stable conditions
- 🟡 **Medium** (40-59): Monitor closely
- 🟠 **High** (60-79): Take action
- 🔴 **Critical** (80-100): Immediate attention needed

## 🏗 Architecture

```
upstream-alert
├── sources/          ← Data source adapters (pure HTTP)
│   ├── fred.py       ← CPI/PPI from FRED
│   ├── gdelt.py      ← News from GDELT (free)
│   ├── comtrade.py   ← Trade data from UN
│   ├── worldbank.py  ← Indicators from World Bank (free)
│   ├── newsdata.py   ← News from NewsData.io
│   └── fbx.py        ← Freight from Freightos
├── engine.py         ← RiskEngine (orchestration + scoring)
├── analyzer.py       ← Gemini AI analysis wrapper
├── models.py         ← Pydantic data models
└── cli.py            ← Click CLI
```

**Design principles:**
- 🚫 No Firebase / cloud dependency
- 🔑 Bring Your Own Keys (BYOK)
- 📦 Zero special system dependencies
- 🎯 Stateless — no database needed

## 🤝 Contributing

```bash
git clone https://github.com/ImL1s/upstream-alert
cd upstream-alert
pip install -e ".[dev]"
pytest
```

## 📄 License

MIT — use freely in personal and commercial projects.

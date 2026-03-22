"""E2E smoke tests — subprocess-level validation.

These tests run the CLI and OpenClaw script as subprocesses,
verifying the REAL output format that downstream consumers depend on.
They catch issues that unit tests miss:
  - import errors in the installed package
  - JSON serialization bugs with real data types (datetime, Enum)
  - CLI exit codes and output structure
  - check_risk.py protocol compliance for OpenClaw
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Project root for the opensource package
PROJ_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = PROJ_ROOT / "skills" / "openclaw" / "scripts" / "check_risk.py"


def _run(cmd: list[str], timeout: int = 60, **kwargs) -> subprocess.CompletedProcess:
    """Run a command with the current Python and return result."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    # Ensure upstream-alert is importable
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env, **kwargs,
    )


# ── CLI smoke tests ──


class TestCLISmoke:
    """Test the installed `upstream-alert` CLI commands."""

    def test_version(self):
        r = _run([sys.executable, "-m", "upstream_alert.cli", "--version"])
        # click version option may exit 0
        assert r.returncode == 0
        assert "0.1.0" in r.stdout or "0.1.0" in r.stderr

    def test_help(self):
        r = _run([sys.executable, "-m", "upstream_alert.cli", "--help"])
        assert r.returncode == 0
        assert "supply chain" in r.stdout.lower() or "risk" in r.stdout.lower()

    def test_sources_command(self):
        r = _run([sys.executable, "-m", "upstream_alert.cli", "sources"])
        assert r.returncode == 0
        assert "FRED" in r.stdout
        assert "GDELT" in r.stdout
        assert "GEMINI_API_KEY" in r.stdout

    def test_check_json_output_structure(self):
        """The --json-output flag must produce valid JSON with required fields."""
        r = _run([
            sys.executable, "-m", "upstream_alert.cli",
            "check", "coffee", "-c", "US", "-j",
        ])
        assert r.returncode == 0

        # stdout may contain non-JSON prefix (the "Checking..." line)
        lines = r.stdout.strip().split("\n")
        # Find the JSON part (starts with '{')
        json_lines = []
        in_json = False
        for line in lines:
            if line.strip().startswith("{"):
                in_json = True
            if in_json:
                json_lines.append(line)

        json_str = "\n".join(json_lines)
        data = json.loads(json_str)

        # Validate required fields exist
        assert "item" in data
        assert "country" in data
        assert "score" in data
        assert "level" in data
        assert isinstance(data["score"], int)
        assert data["level"] in ("low", "medium", "high", "critical")
        assert 0 <= data["score"] <= 100
        assert isinstance(data.get("checked_at", ""), str)

    def test_check_text_output_has_emoji(self):
        """Human-readable output should include the risk emoji."""
        r = _run([
            sys.executable, "-m", "upstream_alert.cli",
            "check", "rice", "-c", "JP",
        ])
        assert r.returncode == 0
        # Should contain one of the risk emojis
        assert any(e in r.stdout for e in ("🟢", "🟡", "🟠", "🔴"))
        assert "/100" in r.stdout

    def test_pulse_command(self):
        r = _run([
            sys.executable, "-m", "upstream_alert.cli",
            "pulse", "-c", "US",
        ])
        assert r.returncode == 0
        assert "Market Pulse" in r.stdout or "Freight" in r.stdout


# ── OpenClaw script protocol tests ──


class TestOpenClawScript:
    """Test check_risk.py conforms to the OpenClaw exec protocol.

    Protocol requirements:
      - stdout = valid JSON
      - exit 0 on success, exit 1 on error
      - JSON must have 'status' field
      - Success JSON must have: item, country, score, level, brief
    """

    @pytest.mark.skipif(
        not SCRIPT_PATH.exists(),
        reason=f"OpenClaw script not found at {SCRIPT_PATH}",
    )
    def test_no_args_returns_error_json(self):
        """No arguments → exit 1 + error JSON."""
        r = _run([sys.executable, str(SCRIPT_PATH)])
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert "error" in data

    @pytest.mark.skipif(
        not SCRIPT_PATH.exists(),
        reason=f"OpenClaw script not found at {SCRIPT_PATH}",
    )
    def test_success_json_structure(self):
        """check_risk.py <item> <country> → valid JSON with all required fields."""
        r = _run([sys.executable, str(SCRIPT_PATH), "coffee", "US"])
        assert r.returncode == 0

        data = json.loads(r.stdout)

        # Protocol-mandated fields
        assert data["status"] == "ok"
        assert data["item"] == "coffee"
        assert data["country"] == "US"
        assert isinstance(data["score"], int)
        assert 0 <= data["score"] <= 100
        assert data["level"] in ("low", "medium", "high", "critical")
        assert isinstance(data["brief"], str)
        assert len(data["brief"]) > 0

        # Optional but expected
        assert "ai_summary" in data
        assert "sources_used" in data
        assert isinstance(data["sources_used"], list)
        assert "errors" in data
        assert isinstance(data["errors"], list)

    @pytest.mark.skipif(
        not SCRIPT_PATH.exists(),
        reason=f"OpenClaw script not found at {SCRIPT_PATH}",
    )
    def test_unicode_item_name(self):
        """CJK item names must work end-to-end."""
        r = _run([sys.executable, str(SCRIPT_PATH), "咖啡豆", "TW"])
        assert r.returncode == 0

        data = json.loads(r.stdout)
        assert data["status"] == "ok"
        assert data["item"] == "咖啡豆"

    @pytest.mark.skipif(
        not SCRIPT_PATH.exists(),
        reason=f"OpenClaw script not found at {SCRIPT_PATH}",
    )
    def test_default_country_is_tw(self):
        """If no country given, should default to TW."""
        r = _run([sys.executable, str(SCRIPT_PATH), "rice"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["country"] == "TW"

    @pytest.mark.skipif(
        not SCRIPT_PATH.exists(),
        reason=f"OpenClaw script not found at {SCRIPT_PATH}",
    )
    def test_market_pulse_structure(self):
        """If market_pulse is present, its structure must be correct."""
        r = _run([sys.executable, str(SCRIPT_PATH), "steel", "US"])
        assert r.returncode == 0
        data = json.loads(r.stdout)

        if "market_pulse" in data and data["market_pulse"] is not None:
            mp = data["market_pulse"]
            assert "cpi_change" in mp
            assert isinstance(mp["cpi_change"], (int, float))
            # freight_index may be None if mock
            if mp.get("freight_index") is not None:
                assert isinstance(mp["freight_index"], (int, float))


# ── Python API smoke tests ──


class TestPythonAPISmoke:
    """Test the public Python API (from upstream_alert import ...)."""

    def test_import_package(self):
        """Package should be importable without side effects."""
        import upstream_alert

        assert hasattr(upstream_alert, "__version__")
        assert upstream_alert.__version__ == "0.1.0"
        assert hasattr(upstream_alert, "RiskEngine")
        assert hasattr(upstream_alert, "check_risk")

    def test_risk_engine_instantiation(self):
        """Engine should instantiate without any API keys."""
        from upstream_alert import RiskEngine

        engine = RiskEngine()
        assert engine is not None

    def test_models_importable(self):
        """Public models should be importable from the package."""
        from upstream_alert import (
            NewsSignal,
            PriceSignal,
            RiskLevel,
            RiskResult,
        )
        # Also importable from submodules
        from upstream_alert.models import (
            FreightSignal,
            MarketPulse,
            TradeSignal,
        )

        assert RiskLevel.LOW.value == "low"
        assert PriceSignal(source="test", period="2026", category="CPI")
        assert FreightSignal(index=100, source="test")

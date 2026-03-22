"""upstream-alert CLI.

Usage:
    upstream-alert check "咖啡豆" --country TW
    upstream-alert pulse
    upstream-alert sources
"""

from __future__ import annotations

import json
import os
import sys

import click

from upstream_alert import __version__


@click.group()
@click.version_option(__version__)
def main():
    """🔍 Supply chain risk monitoring engine."""
    pass


@main.command()
@click.argument("item")
@click.option("--country", "-c", default="TW", help="ISO2 country code (default: TW)")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def check(item: str, country: str, json_output: bool):
    """Check supply chain risk for an item.

    Examples:
        upstream-alert check "咖啡豆" --country TW
        upstream-alert check coffee -c US -j
    """
    from upstream_alert.engine import RiskEngine

    engine = RiskEngine()
    click.echo(f"🔍 Checking risk for '{item}' ({country})...\n")

    result = engine.check(item, country)

    if json_output:
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        click.echo(result.to_brief())
        click.echo()

        if result.ai_summary:
            click.echo("📊 Analysis:")
            click.echo(result.ai_summary)
            click.echo()

        if result.market_pulse:
            pulse = result.market_pulse
            click.echo("📈 Market Pulse:")
            if pulse.freight:
                trend = "↑" if pulse.freight.change_pct > 0 else "↓"
                click.echo(
                    f"  🚢 Freight: {pulse.freight.index:.0f} "
                    f"({trend}{abs(pulse.freight.change_pct):.1f}%)"
                )
            if pulse.cpi_change is not None:
                click.echo(f"  📊 CPI: {pulse.cpi_change:+.1f}% YoY")
            click.echo()

        if result.sources_used:
            click.echo(f"📡 Sources: {', '.join(result.sources_used)}")

        if result.errors:
            click.echo(f"\n⚠️  Warnings: {len(result.errors)}")
            for e in result.errors:
                click.echo(f"   - {e}")


@main.command()
@click.option("--country", "-c", default="TW", help="Country code")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def pulse(country: str, json_output: bool):
    """Show current market pulse (freight, CPI, PMI)."""
    from upstream_alert.sources import fbx, fred, worldbank

    click.echo("📊 Market Pulse\n")

    # Freight
    freight_key = os.environ.get("FBX_API_KEY")
    freight = fbx.fetch_global_index(freight_key)
    if json_output:
        click.echo(json.dumps(freight.model_dump(), ensure_ascii=False, indent=2))
    else:
        trend = "↑" if freight.change_pct > 0 else "↓"
        src = " (mock)" if freight.source == "mock" else ""
        click.echo(
            f"  🚢 Freight Index: {freight.index:.0f} "
            f"({trend}{abs(freight.change_pct):.1f}%){src}"
        )

    # CPI
    fred_key = os.environ.get("FRED_API_KEY", "")
    if fred_key:
        series_map = fred.COUNTRY_SERIES.get(country.upper(), {})
        cpi_series = series_map.get("cpi", "")
        if cpi_series:
            cpi = fred.get_latest_cpi_change(fred_key, cpi_series)
            click.echo(f"  📈 CPI: {cpi:+.1f}% YoY (FRED)")
    else:
        cpi = worldbank.get_latest_cpi(country)
        if cpi:
            click.echo(f"  📈 CPI: {cpi:+.1f}% YoY (World Bank)")

    click.echo()


@main.command()
def sources():
    """Show configured data sources and API key status."""
    keys = {
        "FRED_API_KEY": ("FRED (CPI/PPI)", "https://fred.stlouisfed.org/docs/api/api_key.html"),
        "COMTRADE_API_KEY": ("UN Comtrade (Trade)", "https://comtradeplus.un.org/"),
        "NEWSDATA_API_KEY": ("NewsData.io (News)", "https://newsdata.io/"),
        "GEMINI_API_KEY": ("Gemini AI (Analysis)", "https://aistudio.google.com/apikey"),
        "FBX_API_KEY": ("Freightos FBX (Freight)", "Paid: $119/mo"),
    }
    free_sources = [
        ("GDELT (News)", "No key required", "https://api.gdeltproject.org"),
        ("World Bank (Indicators)", "No key required", "https://api.worldbank.org"),
    ]

    click.echo("📡 Data Sources\n")
    click.echo("  API Key Sources:")
    for env_var, (name, url) in keys.items():
        configured = "✅" if os.environ.get(env_var) else "❌"
        click.echo(f"    {configured} {name} ({env_var})")

    click.echo("\n  Free Sources (no key needed):")
    for name, note, url in free_sources:
        click.echo(f"    ✅ {name}")

    click.echo("\n💡 Set API keys as environment variables or in .env file")


if __name__ == "__main__":
    main()

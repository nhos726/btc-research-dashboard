"""Headless collector for GitHub Actions.

Fetches the same public sources used by the Streamlit dashboard and writes a
machine-readable point-in-time snapshot. A failure in one source is recorded in
``errors`` and does not prevent the other observations from being saved.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

from collectors.derivatives import fetch_delivery_basis, fetch_derivatives
from collectors.etf_flows import fetch_etf_flows
from collectors.exchange_flows import fetch_exchange_flows
from collectors.options import fetch_options_summary
from collectors.spot import fetch_daily_ohlcv, fetch_market_snapshot
from collectors.stablecoins import fetch_stablecoin_summary
from indicators import attach_confirmed_indicators, completed_daily_candles, enrich_ohlcv, overview_from_prices
from market_state import build_market_state
from snapshot import build_snapshot, snapshot_json

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
LATEST_PATH = DATA_DIR / "latest_snapshot.json"


def collect() -> dict:
    result: dict = {}
    errors: dict[str, str] = {}
    loaders = {
        "market": fetch_market_snapshot,
        "spot": fetch_daily_ohlcv,
        "derivatives": fetch_derivatives,
        "delivery": fetch_delivery_basis,
        "options": fetch_options_summary,
        "stablecoins": fetch_stablecoin_summary,
        "etf_flows": fetch_etf_flows,
        "exchange_flows": fetch_exchange_flows,
    }
    for name, loader in loaders.items():
        try:
            result[name] = loader()
        except Exception as exc:  # keep partial snapshots by design
            errors[name] = f"{type(exc).__name__}: {exc}"

    technical = {}
    if "spot" in result:
        spot_df, _ = result["spot"]
        confirmed = completed_daily_candles(spot_df)
        confirmed_enriched = enrich_ohlcv(confirmed)
        technical = overview_from_prices(confirmed_enriched)

    market = result.get("market", ({}, None))[0]
    deriv = result["derivatives"][0] if "derivatives" in result else None
    oi = result["derivatives"][1] if "derivatives" in result else None
    options = result["options"][0] if "options" in result else None
    delivery = result["delivery"][0] if "delivery" in result else None
    states = build_market_state(technical, deriv, oi, options, delivery)

    source_times = {
        "market": result.get("market", (None, None))[1],
        "spot": result.get("spot", (None, None))[1],
        "derivatives": result.get("derivatives", (None, None, None, None))[3],
        "delivery": result.get("delivery", (None, None))[1],
        "options": result.get("options", (None, None, None))[2],
        "stablecoins": result.get("stablecoins", (None, None, None))[2],
        "etf_flows": result.get("etf_flows", (None, None, None))[2],
        "exchange_flows": result.get("exchange_flows", (None, None, None))[2],
    }
    return build_snapshot(
        market=market,
        technical=technical,
        states=states,
        deriv=deriv,
        options=options,
        stablecoins=result["stablecoins"][0] if "stablecoins" in result else None,
        etf=result["etf_flows"][0] if "etf_flows" in result else None,
        exchange_flows=result["exchange_flows"][0] if "exchange_flows" in result else None,
        delivery=delivery,
        source_times=source_times,
        errors=errors,
    )


def write_snapshot(snapshot: dict) -> tuple[Path, Path]:
    observed = datetime.fromisoformat(snapshot["observed_at"].replace("Z", "+00:00"))
    observed = observed.astimezone(timezone.utc)
    # One canonical hourly file. Re-runs within an hour intentionally replace it,
    # while latest_snapshot.json always points to the newest successful run.
    history_path = HISTORY_DIR / observed.strftime("%Y/%m/%d") / f"{observed:%H}.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    text = snapshot_json(snapshot) + "\n"
    LATEST_PATH.write_text(text, encoding="utf-8")
    history_path.write_text(text, encoding="utf-8")
    return LATEST_PATH, history_path


if __name__ == "__main__":
    snapshot = collect()
    latest, history = write_snapshot(snapshot)
    print(f"wrote {latest.relative_to(ROOT)}")
    print(f"wrote {history.relative_to(ROOT)}")
    print(json.dumps({"observed_at": snapshot.get("observed_at"), "errors": snapshot.get("errors", {})}, ensure_ascii=False))

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from collectors.http import DataSourceError, get_json

CHART_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
LIST_URL = "https://stablecoins.llama.fi/stablecoins"


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _supply(row: dict) -> float | None:
    # DefiLlama's chart endpoint exposes peggedUSD values as objects.
    for key in ("totalCirculatingUSD", "totalCirculating"):
        value = row.get(key)
        if isinstance(value, dict):
            n = _num(value.get("peggedUSD"))
            if n is not None:
                return n
        n = _num(value)
        if n is not None:
            return n
    return None


def _change(series: pd.Series, days: int) -> float | None:
    if series.empty:
        return None
    latest_date = series.index[-1]
    target = latest_date - pd.Timedelta(days=days)
    prior = series.loc[series.index <= target]
    if prior.empty:
        return None
    old, new = float(prior.iloc[-1]), float(series.iloc[-1])
    return None if old == 0 else (new / old - 1.0) * 100.0


def _symbol_cap(asset: dict) -> float | None:
    value = asset.get("circulating")
    if isinstance(value, dict):
        return _num(value.get("peggedUSD"))
    return _num(value)


def fetch_stablecoin_summary():
    """USD-pegged stablecoin supply proxy from DefiLlama.

    The historical series uses DefiLlama's peggedUSD circulating field. It is
    kept separate from any spot-price-marked market-cap interpretation so a
    depeg is not silently treated as redemption.
    """
    raw = get_json(CHART_URL)
    if not isinstance(raw, list):
        raise DataSourceError("Unexpected DefiLlama stablecoin chart response")

    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ts = _num(item.get("date"))
        value = _supply(item)
        if ts is None or value is None:
            continue
        rows.append((pd.to_datetime(ts, unit="s", utc=True), value))
    if not rows:
        raise DataSourceError("No usable DefiLlama stablecoin history")

    history = pd.DataFrame(rows, columns=["date", "supply_usd"]).drop_duplicates("date").set_index("date").sort_index()
    series = history["supply_usd"]
    latest = float(series.iloc[-1])
    stats = {
        "total_supply_usd": latest,
        "change_7d": _change(series, 7),
        "change_30d": _change(series, 30),
        "change_90d": _change(series, 90),
        "usdt_dominance": None,
    }

    # Dominance is useful context but non-essential. A schema/API failure here
    # must not take down the historical stablecoin panel.
    try:
        listing = get_json(LIST_URL, params={"includePrices": "true"})
        assets = listing.get("peggedAssets", []) if isinstance(listing, dict) else []
        usdt = next((a for a in assets if str(a.get("symbol", "")).upper() == "USDT"), None)
        usdt_supply = _symbol_cap(usdt) if usdt else None
        if usdt_supply is not None and latest > 0:
            stats["usdt_dominance"] = usdt_supply / latest * 100.0
    except Exception:
        pass

    updated = history.index[-1].to_pydatetime()
    return stats, history, updated

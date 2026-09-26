from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from config import SETTINGS
from collectors.http import DataSourceError

COINMETRICS_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
METRICS = "FlowInExNtv,FlowOutExNtv,FlowInExUSD,FlowOutExUSD"


def fetch_exchange_flows(days: int = 120):
    """Fetch aggregate BTC exchange inflows/outflows from Coin Metrics Community API.

    Netflow is calculated locally as inflow - outflow. The Ex metrics aggregate
    exchange activity identified by Coin Metrics; they are not a single-venue feed.
    """
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days + 10)).date().isoformat()
    params = {
        "assets": "btc",
        "metrics": METRICS,
        "frequency": "1d",
        "start_time": start,
        "page_size": 1000,
    }
    try:
        response = requests.get(
            COINMETRICS_URL,
            params=params,
            timeout=SETTINGS.request_timeout,
            headers={"User-Agent": "BTC-Research-Dashboard/0.3.0"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DataSourceError(f"Coin Metrics request failed: {type(exc).__name__}") from exc

    try:
        rows = response.json().get("data", [])
    except ValueError as exc:
        raise DataSourceError("Coin Metrics returned invalid JSON") from exc
    if not rows:
        raise DataSourceError("Coin Metrics exchange-flow response contained no rows")

    df = pd.DataFrame(rows)
    required = ["time", "FlowInExNtv", "FlowOutExNtv", "FlowInExUSD", "FlowOutExUSD"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataSourceError(f"Coin Metrics exchange-flow fields missing: {', '.join(missing)}")

    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    for c in required[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["time", "FlowInExNtv", "FlowOutExNtv"]).sort_values("time")
    df = df.drop_duplicates("time", keep="last").set_index("time")
    if df.empty:
        raise DataSourceError("Coin Metrics exchange-flow rows were not usable")

    df["Netflow_BTC"] = df["FlowInExNtv"] - df["FlowOutExNtv"]
    df["Netflow_USD"] = df["FlowInExUSD"] - df["FlowOutExUSD"]
    df = df.tail(days)

    latest_date = df.index[-1]
    summary = {
        "latest_date": latest_date,
        "latest_netflow_btc": float(df["Netflow_BTC"].iloc[-1]),
        "seven_day_netflow_btc": float(df["Netflow_BTC"].tail(7).sum()),
        "thirty_day_netflow_btc": float(df["Netflow_BTC"].tail(30).sum()),
        "latest_inflow_btc": float(df["FlowInExNtv"].iloc[-1]),
        "latest_outflow_btc": float(df["FlowOutExNtv"].iloc[-1]),
    }
    return summary, df, datetime.now(timezone.utc)

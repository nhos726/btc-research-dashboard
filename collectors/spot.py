from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from collectors.http import DataSourceError, get_json
from config import SETTINGS


def fetch_market_snapshot() -> tuple[dict, datetime]:
    data = get_json(
        f"{SETTINGS.coingecko_base}/coins/bitcoin",
        {"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false"},
    )
    market = data.get("market_data", {})
    usd = market.get("current_price", {}).get("usd")
    if usd is None:
        raise DataSourceError("CoinGecko response has no USD price")
    updated = pd.to_datetime(data.get("last_updated"), utc=True).to_pydatetime()
    return {
        "price_usd": float(usd),
        "change_24h": market.get("price_change_percentage_24h"),
        "change_7d": market.get("price_change_percentage_7d"),
        "ath_usd": market.get("ath", {}).get("usd"),
        "ath_change_pct": market.get("ath_change_percentage", {}).get("usd"),
    }, updated


def fetch_daily_ohlcv(limit: int = 1000) -> tuple[pd.DataFrame, datetime]:
    rows = get_json(
        f"{SETTINGS.binance_spot_base}/api/v3/klines",
        {"symbol": SETTINGS.spot_symbol, "interval": "1d", "limit": limit},
    )
    if not isinstance(rows, list) or not rows:
        raise DataSourceError("Binance returned no spot candles")
    columns = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"]
    df = pd.DataFrame(rows, columns=columns)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time_dt"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    df = df.set_index("date").sort_index()
    # Record when the API observation was actually acquired. The latest candle
    # close_time may be in the future while that UTC daily candle is still open.
    updated = datetime.now(timezone.utc)
    return df, updated


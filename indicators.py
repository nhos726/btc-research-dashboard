from __future__ import annotations

import numpy as np
import pandas as pd

INDICATOR_COLUMNS = ["ma50", "ma200", "high52w", "ma50w", "rsi14", "atr14", "rv30"]


def enrich_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate daily indicators on the rows supplied.

    The caller is responsible for supplying only completed daily candles when
    these values are used as research metrics.
    """
    out = df.copy()
    close = out["close"]
    out["ma50"] = close.rolling(50).mean()
    out["ma200"] = close.rolling(200).mean()
    out["high52w"] = out["high"].rolling(365).max()
    weekly = close.resample("W-SUN").last()
    weekly_ma = weekly.rolling(50).mean()
    out["ma50w"] = weekly_ma.reindex(out.index, method="ffill")
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi14"] = 100 - 100 / (1 + rs)
    out.loc[(loss == 0) & (gain > 0), "rsi14"] = 100.0
    out.loc[(loss == 0) & (gain == 0), "rsi14"] = 50.0
    prev = close.shift(1)
    true_range = pd.concat(
        [(out["high"] - out["low"]), (out["high"] - prev).abs(), (out["low"] - prev).abs()], axis=1
    ).max(axis=1)
    out["atr14"] = true_range.ewm(alpha=1 / 14, adjust=False).mean()
    out["rv30"] = np.log(close / close.shift(1)).rolling(30).std(ddof=1) * np.sqrt(365) * 100
    return out


def completed_daily_candles(df: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Return only candles whose Binance close time has passed."""
    if "close_time_dt" not in df.columns:
        return df.copy()
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    return df[df["close_time_dt"] <= now].copy()


def attach_confirmed_indicators(display_df: pd.DataFrame, confirmed_df: pd.DataFrame) -> pd.DataFrame:
    """Attach confirmed indicators to all display rows, carrying the last value
    forward over an in-progress candle so the live price can still be charted.
    """
    out = display_df.copy()
    enriched = enrich_ohlcv(confirmed_df)
    for col in INDICATOR_COLUMNS:
        out[col] = enriched[col].reindex(out.index).ffill()
    return out


def overview_from_prices(df: pd.DataFrame) -> dict:
    row = df.iloc[-1]
    price = row["close"]
    distance = lambda x: (price / x - 1) * 100 if pd.notna(x) and x else None
    return {
        "close": price,
        "distance_52w": distance(row["high52w"]),
        "distance_ma50": distance(row["ma50"]),
        "distance_ma200": distance(row["ma200"]),
        "distance_ma50w": distance(row["ma50w"]),
        "rv30": row["rv30"],
        "rsi14": row["rsi14"],
        "atr14_pct": row["atr14"] / price * 100,
    }

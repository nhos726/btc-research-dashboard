from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from collectors.http import DataSourceError, get_json
from config import SETTINGS


def fetch_derivatives() -> tuple[dict, pd.DataFrame, pd.DataFrame, datetime]:
    base = SETTINGS.binance_futures_base
    symbol = SETTINGS.futures_pair
    premium = get_json(f"{base}/fapi/v1/premiumIndex", {"symbol": symbol})
    current_oi = get_json(f"{base}/fapi/v1/openInterest", {"symbol": symbol})
    oi_rows = get_json(f"{base}/futures/data/openInterestHist", {"symbol": symbol, "period": "1d", "limit": 31})
    funding_rows = get_json(f"{base}/fapi/v1/fundingRate", {"symbol": symbol, "limit": 90})
    oi = pd.DataFrame(oi_rows)
    if not oi.empty:
        oi["time"] = pd.to_datetime(oi["timestamp"], unit="ms", utc=True)
        oi["oi_usdt"] = pd.to_numeric(oi["sumOpenInterestValue"], errors="coerce")
        oi = oi.set_index("time").sort_index()
    funding = pd.DataFrame(funding_rows)
    if not funding.empty:
        funding["time"] = pd.to_datetime(funding["fundingTime"], unit="ms", utc=True)
        funding["funding_rate"] = pd.to_numeric(funding["fundingRate"], errors="coerce")
        funding = funding.set_index("time").sort_index()
    mark = float(premium["markPrice"])
    index = float(premium["indexPrice"])
    stats = {
        "open_interest_btc": float(current_oi["openInterest"]),
        "open_interest_usd": float(current_oi["openInterest"]) * mark,
        "oi_change_24h": _period_change(oi.get("oi_usdt"), 1),
        "oi_change_7d": _period_change(oi.get("oi_usdt"), 7),
        "funding_rate": float(premium["lastFundingRate"]),
        "mark_price": mark,
        "index_price": index,
        "spot_perp_basis_pct": (mark / index - 1) * 100 if index else None,
    }
    updated = datetime.fromtimestamp(int(premium["time"]) / 1000, tz=timezone.utc)
    return stats, oi, funding, updated


def _period_change(series: pd.Series | None, periods: int) -> float | None:
    if series is None or len(series.dropna()) <= periods:
        return None
    values = series.dropna()
    return (values.iloc[-1] / values.iloc[-1 - periods] - 1) * 100


def fetch_delivery_basis() -> tuple[pd.DataFrame, datetime]:
    base = SETTINGS.binance_futures_base
    info = get_json(f"{base}/fapi/v1/exchangeInfo")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    contracts = [s for s in info.get("symbols", []) if s.get("baseAsset") == "BTC" and s.get("contractType") in {"CURRENT_QUARTER", "NEXT_QUARTER"} and int(s.get("deliveryDate", 0)) > now_ms]
    rows = []
    for contract in contracts:
        premium = get_json(f"{base}/fapi/v1/premiumIndex", {"symbol": contract["symbol"]})
        expiry = pd.to_datetime(contract["deliveryDate"], unit="ms", utc=True)
        days = max((expiry - pd.Timestamp.now(tz="UTC")).total_seconds() / 86400, 0.01)
        price, index_price = float(premium["markPrice"]), float(premium["indexPrice"])
        rows.append({"contract": contract["symbol"], "expiry": expiry, "days": days, "price": price, "basis_pct": (price / index_price - 1) * 100, "annualized_basis_pct": (price / index_price - 1) * 365 / days * 100})
    return pd.DataFrame(rows), datetime.now(timezone.utc)


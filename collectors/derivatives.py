from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from collectors.http import DataSourceError, get_json
from config import SETTINGS


def _deribit(path: str, params: dict | None = None):
    payload = get_json(f"{SETTINGS.deribit_base}/public/{path}", params)
    if not isinstance(payload, dict) or "result" not in payload:
        raise DataSourceError("Deribit returned an unexpected response")
    if payload.get("error"):
        raise DataSourceError("Deribit API returned an error")
    return payload["result"]


def fetch_derivatives() -> tuple[dict, pd.DataFrame, pd.DataFrame, datetime]:
    """Fetch cloud-safe BTC perpetual positioning inputs from Deribit.

    Deribit is already used by the options collector and is reachable from the
    deployed Streamlit app.  Unlike the old Binance implementation, free public
    Deribit endpoints do not provide the 30-day OI history used by this dashboard,
    so OI is reported as a current snapshot and the Market State positioning card
    classifies funding only.  No OI history/change is fabricated.
    """
    summaries = _deribit("get_book_summary_by_currency", {"currency": "BTC", "kind": "future"})
    perp = next((x for x in summaries if x.get("instrument_name") == "BTC-PERPETUAL"), None)
    if not perp:
        raise DataSourceError("Deribit BTC-PERPETUAL summary unavailable")

    mark = _num(perp.get("mark_price"))
    index = _num(perp.get("underlying_price")) or _num(perp.get("estimated_delivery_price"))
    funding_rate = _num(perp.get("funding_8h"))
    current_funding = _num(perp.get("current_funding"))
    open_interest = _num(perp.get("open_interest"))

    now = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(days=30)).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)
    history_rows = _deribit("get_funding_rate_history", {
        "instrument_name": "BTC-PERPETUAL",
        "start_timestamp": start_ms,
        "end_timestamp": end_ms,
    })
    funding = pd.DataFrame(history_rows)
    if not funding.empty:
        funding["time"] = pd.to_datetime(funding["timestamp"], unit="ms", utc=True)
        # Deribit exposes the 8-hour-equivalent interest as interest_8h.
        funding["funding_rate"] = pd.to_numeric(funding.get("interest_8h"), errors="coerce")
        funding = funding.set_index("time").sort_index()

    stats = {
        "venue": "Deribit",
        "open_interest_contracts": open_interest,
        "open_interest_usd": None,
        "oi_change_24h": None,
        "oi_change_7d": None,
        "funding_rate": funding_rate,
        "current_funding": current_funding,
        "mark_price": mark,
        "index_price": index,
        "spot_perp_basis_pct": (mark / index - 1) * 100 if mark and index else None,
    }
    oi = pd.DataFrame()  # intentionally unavailable from the chosen free endpoint
    updated_ms = perp.get("creation_timestamp")
    updated = datetime.fromtimestamp(int(updated_ms) / 1000, tz=timezone.utc) if updated_ms else now
    return stats, oi, funding, updated


def fetch_delivery_basis() -> tuple[pd.DataFrame, datetime]:
    """Build the current Deribit BTC dated-futures curve from public summaries."""
    summaries = _deribit("get_book_summary_by_currency", {"currency": "BTC", "kind": "future"})
    instruments = _deribit("get_instruments", {"currency": "BTC", "kind": "future", "expired": "false"})
    expiry_by_name = {
        x.get("instrument_name"): x.get("expiration_timestamp")
        for x in instruments
        if x.get("instrument_name") and x.get("instrument_name") != "BTC-PERPETUAL"
    }
    now = pd.Timestamp.now(tz="UTC")
    rows = []
    for item in summaries:
        name = item.get("instrument_name")
        expiry_ms = expiry_by_name.get(name)
        if not name or name == "BTC-PERPETUAL" or not expiry_ms:
            continue
        expiry = pd.to_datetime(expiry_ms, unit="ms", utc=True)
        days = (expiry - now).total_seconds() / 86400
        price = _num(item.get("mark_price"))
        index_price = _num(item.get("underlying_price")) or _num(item.get("estimated_delivery_price"))
        if days <= 0 or not price or not index_price:
            continue
        basis = (price / index_price - 1) * 100
        rows.append({
            "contract": name,
            "expiry": expiry,
            "days": days,
            "price": price,
            "basis_pct": basis,
            "annualized_basis_pct": basis * 365 / days,
        })
    return pd.DataFrame(rows).sort_values("days") if rows else pd.DataFrame(), datetime.now(timezone.utc)


def _num(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None

# Kept for backward-compatible unit tests and possible future historical OI sources.
def _period_change(series: pd.Series | None, periods: int) -> float | None:
    if series is None or len(series.dropna()) <= periods:
        return None
    values = series.dropna()
    return (values.iloc[-1] / values.iloc[-1 - periods] - 1) * 100

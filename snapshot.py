from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from typing import Any

import pandas as pd


def _clean(value: Any):
    """Convert pandas/numpy/datetime values into strict JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert("UTC").isoformat()
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_snapshot(*, market: dict, technical: dict, states: list[dict], deriv: dict | None,
                   options: dict | None, stablecoins: dict | None, etf: dict | None,
                   exchange_flows: dict | None, delivery: pd.DataFrame | None,
                   source_times: dict[str, Any], errors: dict[str, str]) -> dict:
    curve = []
    if delivery is not None and not delivery.empty:
        for _, row in delivery.sort_values("days").iterrows():
            curve.append({
                "contract": row.get("contract"),
                "expiry": row.get("expiry"),
                "days": row.get("days"),
                "basis_pct": row.get("basis_pct"),
                "annualized_basis_pct": row.get("annualized_basis_pct"),
            })

    snapshot = {
        "schema_version": "0.1",
        "dashboard_version": "0.3.8",
        "observed_at": datetime.now(timezone.utc),
        "market": market,
        "technical": technical,
        "market_state": states,
        "derivatives": deriv,
        "dated_futures_curve": curve,
        "options": options,
        "stablecoins": stablecoins,
        "etf_flows": etf,
        "exchange_flows": exchange_flows,
        "source_times": source_times,
        "errors": errors,
    }
    return _clean(snapshot)


def snapshot_json(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False)

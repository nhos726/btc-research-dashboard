from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd

from collectors.http import DataSourceError, get_json
from config import SETTINGS


NAME_RE = re.compile(r"^BTC-(\d{1,2}[A-Z]{3}\d{2})-(\d+)-(C|P)$")


def _order_book_point(instrument_name: str, kind: str) -> dict | None:
    """Return Deribit's own delta and mark IV for one option. Failure is non-fatal."""
    try:
        payload = get_json(
            f"{SETTINGS.deribit_base}/public/get_order_book",
            {"instrument_name": instrument_name, "depth": 1},
        )
        result = payload.get("result", {})
        delta = (result.get("greeks") or {}).get("delta")
        mark_iv = result.get("mark_iv")
        if delta is None or mark_iv is None:
            return None
        return {
            "instrument_name": instrument_name,
            "kind": kind,
            "delta": float(delta),
            "abs_delta": abs(float(delta)),
            "mark_iv": float(mark_iv),
        }
    except Exception:
        return None


def _iv_at_25_delta(points: list[dict], kind: str) -> tuple[float | None, str]:
    """Interpolate mark IV to |delta|=0.25; fall back to a very close observed point."""
    usable = sorted(
        [p for p in points if p and p["kind"] == kind and 0 < p["abs_delta"] < 1],
        key=lambda p: p["abs_delta"],
    )
    if not usable:
        return None, "no usable delta points"

    target = 0.25
    below = [p for p in usable if p["abs_delta"] <= target]
    above = [p for p in usable if p["abs_delta"] >= target]
    if below and above:
        lo, hi = below[-1], above[0]
        if hi["abs_delta"] == lo["abs_delta"]:
            return lo["mark_iv"], f"observed |Δ|={lo['abs_delta']:.3f}"
        # Do not interpolate across an implausibly wide delta gap.
        if target - lo["abs_delta"] <= 0.10 and hi["abs_delta"] - target <= 0.10:
            w = (target - lo["abs_delta"]) / (hi["abs_delta"] - lo["abs_delta"])
            iv = lo["mark_iv"] + w * (hi["mark_iv"] - lo["mark_iv"])
            return float(iv), f"interpolated |Δ| {lo['abs_delta']:.3f}–{hi['abs_delta']:.3f}"

    nearest = min(usable, key=lambda p: abs(p["abs_delta"] - target))
    if abs(nearest["abs_delta"] - target) <= 0.03:
        return nearest["mark_iv"], f"nearest |Δ|={nearest['abs_delta']:.3f}"
    return None, "no point sufficiently close to 25Δ"


def _fetch_25d_rr(expiry_group: pd.DataFrame, underlying: float) -> dict:
    """Compute 25Δ RR = call mark IV - put mark IV for one expiry.

    Candidate strikes are limited to OTM options around spot to keep public API load modest.
    Delta comes from Deribit's get_order_book Greeks; it is never inferred from strike.
    """
    calls = expiry_group[(expiry_group["kind"] == "C") & (expiry_group["strike"] >= underlying)].copy()
    puts = expiry_group[(expiry_group["kind"] == "P") & (expiry_group["strike"] <= underlying)].copy()
    calls["distance"] = (calls["strike"] / underlying - 1).abs()
    puts["distance"] = (puts["strike"] / underlying - 1).abs()
    candidates = pd.concat([calls.nsmallest(16, "distance"), puts.nsmallest(16, "distance")])

    points: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_order_book_point, row.instrument_name, row.kind): row.instrument_name
            for row in candidates.itertuples()
        }
        for future in as_completed(futures):
            point = future.result()
            if point:
                points.append(point)

    call_iv, call_method = _iv_at_25_delta(points, "C")
    put_iv, put_method = _iv_at_25_delta(points, "P")
    if call_iv is None or put_iv is None:
        return {
            "rr_25d": None, "call_25d_iv": call_iv, "put_25d_iv": put_iv,
            "rr_25d_method": f"Call: {call_method}; Put: {put_method}",
            "rr_25d_points": len(points),
        }
    return {
        "rr_25d": float(call_iv - put_iv),
        "call_25d_iv": float(call_iv),
        "put_25d_iv": float(put_iv),
        "rr_25d_method": f"Call: {call_method}; Put: {put_method}",
        "rr_25d_points": len(points),
    }


def fetch_options_summary() -> tuple[dict, pd.DataFrame, datetime]:
    payload = get_json(f"{SETTINGS.deribit_base}/public/get_book_summary_by_currency", {"currency": "BTC", "kind": "option"})
    records = payload.get("result", [])
    parsed = []
    for row in records:
        instrument_name = row.get("instrument_name", "")
        match = NAME_RE.match(instrument_name)
        if not match or row.get("mark_iv") is None or row.get("underlying_price") is None:
            continue
        expiry_s, strike_s, kind = match.groups()
        parsed.append({
            "instrument_name": instrument_name,
            "expiry": pd.to_datetime(expiry_s, format="%d%b%y", utc=True) + pd.Timedelta(hours=8),
            "strike": float(strike_s), "kind": kind, "mark_iv": float(row["mark_iv"]),
            "underlying": float(row["underlying_price"]),
        })
    df = pd.DataFrame(parsed)
    if df.empty:
        raise DataSourceError("Deribit returned no usable option summaries")
    now = pd.Timestamp.now(tz="UTC")
    df = df[df["expiry"] > now].copy()
    df["days"] = (df["expiry"] - now).dt.total_seconds() / 86400
    term_rows = []
    for expiry, group in df.groupby("expiry"):
        underlying = group["underlying"].median()
        strike = group.loc[(group["strike"] - underlying).abs().idxmin(), "strike"]
        atm = group[group["strike"] == strike]
        term_rows.append({"expiry": expiry, "days": atm["days"].median(), "strike": strike, "atm_iv": atm["mark_iv"].mean(), "legs": len(atm)})
    term = pd.DataFrame(term_rows).sort_values("expiry")
    nearest = term.iloc[(term["days"] - 30).abs().argsort()[:1]].iloc[0]
    selected_group = df[df["expiry"] == nearest["expiry"]].copy()
    underlying = float(selected_group["underlying"].median())
    rr = _fetch_25d_rr(selected_group, underlying)
    stats = {
        "atm_30d_iv": float(nearest["atm_iv"]), "atm_30d_expiry": nearest["expiry"],
        "atm_30d_days": float(nearest["days"]), "atm_30d_strike": float(nearest["strike"]),
        "atm_30d_legs": int(nearest["legs"]), **rr,
    }
    return stats, term, datetime.now(timezone.utc)

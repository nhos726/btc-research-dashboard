from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import pandas as pd


def _valid(x: Any) -> bool:
    try:
        return x is not None and not pd.isna(x) and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def classify_trend(distance_ma200, distance_ma50w) -> tuple[str, str]:
    """Classify long-term price location without forecasting direction."""
    if not (_valid(distance_ma200) and _valid(distance_ma50w)):
        return "N/A", "Long-term trend inputs unavailable"
    a, b = float(distance_ma200), float(distance_ma50w)
    if a >= 10 and b >= 10:
        return "Well above long-term trend", f"200d {a:+.1f}% · 50w {b:+.1f}%"
    if a > 0 and b > 0:
        return "Above long-term trend", f"200d {a:+.1f}% · 50w {b:+.1f}%"
    if a <= -10 and b <= -10:
        return "Well below long-term trend", f"200d {a:+.1f}% · 50w {b:+.1f}%"
    if a < 0 and b < 0:
        return "Below long-term trend", f"200d {a:+.1f}% · 50w {b:+.1f}%"
    return "Mixed long-term trend", f"200d {a:+.1f}% · 50w {b:+.1f}%"


def classify_oi_level(current_oi_usd, oi_history: pd.Series | None) -> tuple[str, str]:
    """Classify OI against its available 30-day Binance USDⓈ-M history."""
    if not _valid(current_oi_usd) or oi_history is None:
        return "N/A", "OI level unavailable"
    hist = pd.to_numeric(oi_history, errors="coerce").dropna()
    if len(hist) < 10:
        return "N/A", "Insufficient OI history"
    q25, q75 = hist.quantile([0.25, 0.75])
    x = float(current_oi_usd)
    if x < q25:
        return "Low OI", f"below 30d Q25 (${q25/1e9:.2f}B)"
    if x > q75:
        return "High OI", f"above 30d Q75 (${q75/1e9:.2f}B)"
    return "Mid-range OI", f"within 30d IQR (${q25/1e9:.2f}–${q75/1e9:.2f}B)"


def classify_oi_change(change_24h) -> str:
    if not _valid(change_24h): return "N/A"
    x = float(change_24h)
    if x > 2: return "Building"
    if x < -2: return "Unwinding"
    return "Stable"


def classify_funding(rate) -> tuple[str, str]:
    """Funding rate is decimal per 8h (0.0001 = +0.01%)."""
    if not _valid(rate): return "N/A", "Funding unavailable"
    pct = float(rate) * 100
    if pct < -0.005: label = "Negative"
    elif pct <= 0.005: label = "Neutral"
    elif pct <= 0.02: label = "Positive"
    else: label = "Very positive"
    return label, f"{pct:+.4f}% / 8h"


def classify_positioning(current_oi_usd, oi_history, oi_change_24h, funding_rate, current_oi_contracts=None) -> tuple[str, str]:
    oi_level, oi_detail = classify_oi_level(current_oi_usd, oi_history)
    oi_change = classify_oi_change(oi_change_24h)
    funding, funding_detail = classify_funding(funding_rate)
    # Cloud-safe Deribit fallback: the free public snapshot supplies current OI
    # and funding, but not the 30-day OI history previously used for Binance.
    # We therefore classify funding only and show OI as context rather than
    # inventing an OI level/change.
    if oi_level == "N/A" and oi_change == "N/A" and funding != "N/A":
        detail = f"funding {funding_detail}"
        if _valid(current_oi_contracts):
            detail = f"Deribit perp OI {float(current_oi_contracts):,.0f} contracts · " + detail
        return f"{funding} funding", detail
    parts = [oi_level, oi_change, funding]
    if all(x == "N/A" for x in parts):
        return "N/A", "Positioning inputs unavailable"
    label = " / ".join(parts)
    detail = f"{oi_detail} · 24h OI {oi_change.lower()} · funding {funding_detail}"
    return label, detail


def classify_volatility(rv30) -> tuple[str, str]:
    if not _valid(rv30): return "N/A", "30d realized volatility unavailable"
    x = float(rv30)
    if x < 30: label = "Low realized volatility"
    elif x < 50: label = "Moderate realized volatility"
    elif x < 70: label = "Elevated realized volatility"
    else: label = "High realized volatility"
    return label, f"30d RV {x:.1f}% annualized"


def classify_options(iv, rv, rr=None) -> tuple[str, str]:
    if not (_valid(iv) and _valid(rv)): return "N/A", "IV/RV comparison unavailable"
    spread = float(iv) - float(rv)
    if spread < -5: label = "IV below realized volatility"
    elif spread > 5: label = "IV above realized volatility"
    else: label = "IV near realized volatility"
    detail = f"IV−RV {spread:+.1f} pp"
    if _valid(rr):
        r = float(rr)
        rr_label = "Calls richer" if r > 0.5 else "Puts richer" if r < -0.5 else "RR near balanced"
        label = f"{label} / {rr_label}"
        detail += f" · 25Δ RR {r:+.1f} pp"
    return label, detail


def classify_curve(delivery: pd.DataFrame | None, min_days: float = 7.0) -> tuple[str, str]:
    """Classify the curve using the nearest contract with >= min_days remaining.

    Very short-dated contracts are still displayed in the dashboard, but are
    excluded from Market State because annualizing a tiny near-expiry basis can
    create mechanically extreme percentages.
    """
    if delivery is None or delivery.empty or "annualized_basis_pct" not in delivery:
        return "N/A", "Dated futures basis unavailable"
    frame = delivery.copy()
    if "days" in frame:
        days = pd.to_numeric(frame["days"], errors="coerce")
        frame = frame.loc[days >= min_days].copy()
    if frame.empty:
        return "N/A", f"No dated future with ≥{min_days:.0f}d remaining"
    frame = frame.sort_values("days") if "days" in frame else frame
    vals = pd.to_numeric(frame["annualized_basis_pct"], errors="coerce").dropna()
    if vals.empty: return "N/A", "Dated futures basis unavailable"
    near = float(vals.iloc[0])
    if near < 0: label = "Backwardation"
    elif near < 3: label = "Mild contango"
    elif near < 8: label = "Contango"
    else: label = "Steep contango"
    days_used = float(frame.loc[vals.index[0], "days"]) if "days" in frame else None
    detail = f"nearest ≥{min_days:.0f}d annualized basis {near:+.2f}%"
    if days_used is not None:
        detail += f" · {days_used:.0f}d to expiry"
    return label, detail


def build_market_state(technical: dict, deriv: dict | None, oi: pd.DataFrame | None,
                       opt: dict | None, delivery: pd.DataFrame | None) -> list[dict]:
    trend = classify_trend(technical.get("distance_ma200"), technical.get("distance_ma50w"))
    if deriv is None:
        positioning = ("N/A", "Positioning inputs unavailable")
    else:
        hist = oi.get("oi_usdt") if oi is not None and not oi.empty and "oi_usdt" in oi else None
        positioning = classify_positioning(deriv.get("open_interest_usd"), hist,
                                            deriv.get("oi_change_24h"), deriv.get("funding_rate"),
                                            deriv.get("open_interest_contracts"))
    volatility = classify_volatility(technical.get("rv30"))
    options = classify_options(opt.get("atm_30d_iv") if opt else None, technical.get("rv30"), opt.get("rr_25d") if opt else None)
    curve = classify_curve(delivery)
    return [
        {"name":"Trend", "state":trend[0], "detail":trend[1]},
        {"name":"Positioning", "state":positioning[0], "detail":positioning[1]},
        {"name":"Volatility", "state":volatility[0], "detail":volatility[1]},
        {"name":"Options", "state":options[0], "detail":options[1]},
        {"name":"Futures curve", "state":curve[0], "detail":curve[1]},
    ]

from datetime import datetime, timezone
import json
import pandas as pd

from snapshot import build_snapshot, snapshot_json


def test_snapshot_is_strict_json_and_preserves_missing_as_null():
    curve = pd.DataFrame([{
        "contract": "BTC-09OCT26", "expiry": pd.Timestamp("2026-10-09", tz="UTC"),
        "days": 13.0, "basis_pct": 0.15, "annualized_basis_pct": 4.33,
    }])
    snap = build_snapshot(
        market={"price_usd": 84000.0}, technical={"rv30": 43.0},
        states=[{"name": "Trend", "state": "Above", "detail": "x"}],
        deriv={"open_interest_contracts": 123.0, "oi_change_24h": None},
        options=None, stablecoins=None, etf=None, exchange_flows=None,
        delivery=curve, source_times={"market": datetime(2026, 9, 26, tzinfo=timezone.utc)},
        errors={},
    )
    text = snapshot_json(snap)
    parsed = json.loads(text)
    assert parsed["dashboard_version"] == "0.3.6"
    assert parsed["derivatives"]["oi_change_24h"] is None
    assert parsed["dated_futures_curve"][0]["annualized_basis_pct"] == 4.33

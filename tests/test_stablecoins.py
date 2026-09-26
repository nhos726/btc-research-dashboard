import pandas as pd

from collectors.stablecoins import _change, _supply


def test_supply_prefers_usd_circulating():
    row = {"totalCirculatingUSD": {"peggedUSD": 123.0}, "totalCirculating": {"peggedUSD": 999.0}}
    assert _supply(row) == 123.0


def test_change_uses_observation_at_or_before_target():
    idx = pd.to_datetime(["2026-01-01", "2026-01-08", "2026-01-10"], utc=True)
    s = pd.Series([100.0, 110.0, 121.0], index=idx)
    assert round(_change(s, 7), 6) == 21.0


def test_change_returns_none_without_history():
    idx = pd.to_datetime(["2026-01-10"], utc=True)
    assert _change(pd.Series([100.0], index=idx), 7) is None

import itertools
import pandas as pd

from market_state import (
    build_market_state, classify_curve, classify_funding, classify_oi_change,
    classify_oi_level, classify_options, classify_positioning, classify_trend,
    classify_volatility,
)


def test_oi_level_low_mid_high_and_boundaries():
    h = pd.Series(range(100, 130))
    assert classify_oi_level(90, h)[0] == "Low OI"
    assert classify_oi_level(115, h)[0] == "Mid-range OI"
    assert classify_oi_level(140, h)[0] == "High OI"


def test_positioning_all_36_combinations_are_deterministic():
    # 3 OI levels × 3 OI changes × 4 funding states = 36 explicit combinations.
    hist = pd.Series(range(100, 130), dtype=float)
    oi_values = [90.0, 115.0, 140.0]
    changes = [-3.0, 0.0, 3.0]
    fundings = [-0.0001, 0.0, 0.0001, 0.0003]
    outputs = []
    for oi, change, funding in itertools.product(oi_values, changes, fundings):
        a = classify_positioning(oi, hist, change, funding)
        b = classify_positioning(oi, hist, change, funding)
        assert a == b
        assert "N/A" not in a[0]
        outputs.append(a[0])
    assert len(outputs) == 36
    assert len(set(outputs)) == 36


def test_funding_boundaries_are_exhaustive():
    assert classify_funding(-0.000051)[0] == "Negative"
    assert classify_funding(-0.00005)[0] == "Neutral"
    assert classify_funding(0.00005)[0] == "Neutral"
    assert classify_funding(0.000051)[0] == "Positive"
    assert classify_funding(0.0002)[0] == "Positive"
    assert classify_funding(0.000201)[0] == "Very positive"


def test_oi_change_boundaries():
    assert classify_oi_change(-2.01) == "Unwinding"
    assert classify_oi_change(-2.0) == "Stable"
    assert classify_oi_change(2.0) == "Stable"
    assert classify_oi_change(2.01) == "Building"


def test_other_classifiers_cover_boundaries_and_missing():
    for a, b in [(11, 12), (1, 2), (-11, -12), (-1, -2), (1, -1)]:
        assert classify_trend(a, b)[0] != "N/A"
    for rv in [0, 29.99, 30, 49.99, 50, 69.99, 70, 200]:
        assert classify_volatility(rv)[0] != "N/A"
    for spread in [-10, -5, 0, 5, 10]:
        assert classify_options(40 + spread, 40)[0] != "N/A"
    assert classify_trend(None, 1)[0] == "N/A"
    assert classify_volatility(None)[0] == "N/A"
    assert classify_options(None, 40)[0] == "N/A"


def test_curve_states():
    for x, expected in [(-1,"Backwardation"),(1,"Mild contango"),(5,"Contango"),(10,"Steep contango")]:
        df = pd.DataFrame({"annualized_basis_pct":[x]})
        assert classify_curve(df)[0] == expected


def test_build_market_state_always_returns_five_axes():
    states = build_market_state({}, None, None, None, None)
    assert [x["name"] for x in states] == ["Trend","Positioning","Volatility","Options","Futures curve"]
    assert all(x["state"] == "N/A" for x in states)

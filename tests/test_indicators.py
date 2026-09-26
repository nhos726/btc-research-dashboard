import numpy as np
import pandas as pd

from collectors.derivatives import _period_change
from indicators import attach_confirmed_indicators, completed_daily_candles, enrich_ohlcv, overview_from_prices


def sample(rows=400):
    index = pd.date_range("2025-01-01", periods=rows, tz="UTC")
    close = pd.Series(np.arange(100.0, 100.0 + rows), index=index)
    return pd.DataFrame({"open":close-1,"high":close+2,"low":close-2,"close":close,"volume":1.0}, index=index)


def test_moving_averages_and_distance():
    enriched = enrich_ohlcv(sample())
    assert np.isclose(enriched.ma50.iloc[-1], enriched.close.iloc[-50:].mean())
    assert np.isclose(enriched.ma200.iloc[-1], enriched.close.iloc[-200:].mean())
    overview = overview_from_prices(enriched)
    assert overview["distance_ma50"] > 0
    assert overview["rv30"] >= 0


def test_rsi_trending_series_is_high():
    enriched = enrich_ohlcv(sample())
    assert enriched.rsi14.iloc[-1] == 100.0


def test_52w_high_uses_365_daily_highs():
    df = sample()
    enriched = enrich_ohlcv(df)
    assert np.isclose(enriched.high52w.iloc[-1], df.high.iloc[-365:].max())


def test_50w_ma_is_weekly_close_average():
    df = sample(500)
    enriched = enrich_ohlcv(df)
    weekly = df.close.resample("W-SUN").last()
    expected = weekly.rolling(50).mean().reindex(df.index, method="ffill").iloc[-1]
    assert np.isclose(enriched.ma50w.iloc[-1], expected)


def test_rv30_matches_log_return_definition():
    df = sample()
    enriched = enrich_ohlcv(df)
    expected = np.log(df.close / df.close.shift(1)).rolling(30).std(ddof=1).iloc[-1] * np.sqrt(365) * 100
    assert np.isclose(enriched.rv30.iloc[-1], expected)


def test_atr_is_positive_and_overview_percentage_matches():
    enriched = enrich_ohlcv(sample())
    overview = overview_from_prices(enriched)
    assert enriched.atr14.iloc[-1] > 0
    assert np.isclose(overview["atr14_pct"], enriched.atr14.iloc[-1] / enriched.close.iloc[-1] * 100)


def test_completed_daily_candles_excludes_future_close():
    df = sample(3)
    now = pd.Timestamp("2025-01-03 12:00", tz="UTC")
    df["close_time_dt"] = [
        pd.Timestamp("2025-01-01 23:59", tz="UTC"),
        pd.Timestamp("2025-01-02 23:59", tz="UTC"),
        pd.Timestamp("2025-01-03 23:59", tz="UTC"),
    ]
    result = completed_daily_candles(df, now)
    assert len(result) == 2
    assert result.index[-1] == pd.Timestamp("2025-01-02", tz="UTC")


def test_attach_confirmed_indicators_does_not_use_live_close():
    df = sample(401)
    confirmed = df.iloc[:-1].copy()
    baseline = enrich_ohlcv(confirmed).ma50.iloc[-1]
    df.iloc[-1, df.columns.get_loc("close")] = 1_000_000.0
    display = attach_confirmed_indicators(df, confirmed)
    assert np.isclose(display.ma50.iloc[-1], baseline)


def test_oi_period_change():
    s = pd.Series([100.0, 110.0, 121.0])
    assert np.isclose(_period_change(s, 1), 10.0)
    assert np.isclose(_period_change(s, 2), 21.0)


def test_oi_period_change_returns_none_when_history_is_short():
    assert _period_change(pd.Series([100.0]), 1) is None


def test_overview_52w_distance_uses_latest_confirmed_close():
    enriched = enrich_ohlcv(sample())
    row = enriched.iloc[-1]
    expected = (row.close / row.high52w - 1) * 100
    assert np.isclose(overview_from_prices(enriched)["distance_52w"], expected)

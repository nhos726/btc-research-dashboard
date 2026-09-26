import pandas as pd

import collectors.derivatives as d


def test_fetch_derivatives_deribit(monkeypatch):
    def fake(path, params=None):
        if path == "get_book_summary_by_currency":
            return [{"instrument_name":"BTC-PERPETUAL","mark_price":100100,"underlying_price":100000,
                     "funding_8h":0.0001,"current_funding":0.00001,"open_interest":123456,
                     "creation_timestamp":1700000000000}]
        if path == "get_funding_rate_history":
            return [{"timestamp":1700000000000,"interest_8h":0.0001}]
        raise AssertionError(path)
    monkeypatch.setattr(d, "_deribit", fake)
    stats, oi, funding, updated = d.fetch_derivatives()
    assert stats["venue"] == "Deribit"
    assert stats["open_interest_contracts"] == 123456
    assert round(stats["spot_perp_basis_pct"], 3) == 0.1
    assert oi.empty
    assert funding.iloc[0]["funding_rate"] == 0.0001


def test_fetch_delivery_basis_deribit(monkeypatch):
    def fake(path, params=None):
        if path == "get_book_summary_by_currency":
            return [{"instrument_name":"BTC-31DEC30","mark_price":105000,"underlying_price":100000}]
        if path == "get_instruments":
            return [{"instrument_name":"BTC-31DEC30","expiration_timestamp":1924905600000}]
        raise AssertionError(path)
    monkeypatch.setattr(d, "_deribit", fake)
    frame, _ = d.fetch_delivery_basis()
    assert len(frame) == 1
    assert round(frame.iloc[0]["basis_pct"], 8) == 5.0

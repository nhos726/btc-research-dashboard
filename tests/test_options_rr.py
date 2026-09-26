from collectors.options import _iv_at_25_delta


def test_25d_iv_interpolates():
    pts = [
        {"kind":"C","abs_delta":0.20,"mark_iv":40.0},
        {"kind":"C","abs_delta":0.30,"mark_iv":44.0},
    ]
    iv, method = _iv_at_25_delta(pts, "C")
    assert abs(iv - 42.0) < 1e-9
    assert "interpolated" in method


def test_25d_iv_rejects_distant_point():
    pts = [{"kind":"P","abs_delta":0.10,"mark_iv":50.0}]
    iv, _ = _iv_at_25_delta(pts, "P")
    assert iv is None


def test_25d_iv_accepts_close_observation():
    pts = [{"kind":"P","abs_delta":0.24,"mark_iv":48.0}]
    iv, method = _iv_at_25_delta(pts, "P")
    assert iv == 48.0
    assert "nearest" in method

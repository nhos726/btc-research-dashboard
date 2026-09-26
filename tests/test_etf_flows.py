from collectors.etf_flows import _complete_rows, parse_farside_html


def test_parse_farside_parentheses_and_dash():
    html = '''<table><tr><th>Date</th><th>IBIT</th><th>FBTC</th><th>Total</th></tr>
    <tr><td>24 Sep 2026</td><td>100.0</td><td>(20.5)</td><td>79.5</td></tr>
    <tr><td>25 Sep 2026</td><td>10.0</td><td>-</td><td>10.0</td></tr>
    <tr><td>Total</td><td>110</td><td>(20.5)</td><td>89.5</td></tr></table>'''
    df = parse_farside_html(html)
    assert df.iloc[0]["FBTC"] == -20.5
    assert df.iloc[1]["FBTC"] != df.iloc[1]["FBTC"]  # NaN
    complete = _complete_rows(df)
    assert len(complete) == 1
    assert complete.iloc[0]["Total"] == 79.5

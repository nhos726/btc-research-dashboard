import pandas as pd


def test_netflow_definition():
    df = pd.DataFrame({"inflow": [100.0, 80.0], "outflow": [70.0, 120.0]})
    net = df["inflow"] - df["outflow"]
    assert list(net) == [30.0, -40.0]

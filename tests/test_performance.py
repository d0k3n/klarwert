import pandas as pd
from portfolio.engine import run_engine
from portfolio.performance import xirr, compute_performance


def test_xirr_single_flow_pair():
    flows = [
        (pd.Timestamp("2025-01-01", tz="UTC"), -1000.0),
        (pd.Timestamp("2026-01-01", tz="UTC"), 1100.0),
    ]
    r = xirr(flows)
    assert r is not None
    assert abs(r - 0.10) < 0.001


def test_xirr_no_sign_change_returns_none():
    flows = [
        (pd.Timestamp("2025-01-01", tz="UTC"), -1000.0),
        (pd.Timestamp("2025-06-01", tz="UTC"), -500.0),
    ]
    assert xirr(flows) is None


def test_compute_performance_win_stats():
    df = pd.DataFrame([
        {"datetime": pd.Timestamp("2025-01-01", tz="UTC"), "type": "TRANSFER_INSTANT_INBOUND",
         "tx_type": "DEPOSIT", "name": "", "symbol": "", "asset_class": "",
         "shares": 0.0, "price": 0.0, "amount": 3000.0, "fee": 0.0, "tax": 0.0, "transaction_id": "d1"},
        {"datetime": pd.Timestamp("2025-01-02", tz="UTC"), "type": "BUY", "tx_type": "BUY",
         "name": "W", "symbol": "W", "asset_class": "STOCK", "shares": 10.0, "price": 100.0,
         "amount": -1000.0, "fee": 0.0, "tax": 0.0, "transaction_id": "b1"},
        {"datetime": pd.Timestamp("2025-02-01", tz="UTC"), "type": "SELL", "tx_type": "SELL",
         "name": "W", "symbol": "W", "asset_class": "STOCK", "shares": 10.0, "price": 110.0,
         "amount": 1100.0, "fee": 0.0, "tax": 0.0, "transaction_id": "s1"},
        {"datetime": pd.Timestamp("2025-01-03", tz="UTC"), "type": "BUY", "tx_type": "BUY",
         "name": "L", "symbol": "L", "asset_class": "STOCK", "shares": 10.0, "price": 100.0,
         "amount": -1000.0, "fee": 0.0, "tax": 0.0, "transaction_id": "b2"},
        {"datetime": pd.Timestamp("2025-02-02", tz="UTC"), "type": "SELL", "tx_type": "SELL",
         "name": "L", "symbol": "L", "asset_class": "STOCK", "shares": 10.0, "price": 90.0,
         "amount": 900.0, "fee": 0.0, "tax": 0.0, "transaction_id": "s2"},
    ])
    result = run_engine(df)
    perf = compute_performance(df, result)
    assert perf["winners"] == 1
    assert perf["losers"] == 1
    assert perf["win_rate"] == 50.0
    assert perf["avg_win"] == 100.0
    assert perf["avg_loss"] == -100.0
    assert perf["terminal_value"] == 3000.0
    assert perf["xirr"] is not None

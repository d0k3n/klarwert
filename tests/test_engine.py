import pandas as pd
from portfolio.engine import run_engine


def _make_df(rows):
    return pd.DataFrame(rows)


def test_single_buy():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-02", tz="UTC"), "tx_type": "BUY", "name": "S&P 500", "symbol": "IE00B5BMR087",
         "asset_class": "FUND", "shares": 10.0, "price": 100.0, "amount": -1000.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 1
    op = result["open_positions"][0]
    assert op["shares"] == 10.0
    assert op["average_cost"] == 100.0
    assert op["total_cost"] == 1000.0
    assert len(result["closed_positions"]) == 0


def test_buy_then_full_sell():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "NOVO", "symbol": "DK",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 1.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "NOVO", "symbol": "DK",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 600.0, "fee": 1.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 0
    assert len(result["closed_positions"]) == 1
    cp = result["closed_positions"][0]
    total_cost = 10 * 50 + 1
    total_proceeds = 10 * 60
    expected_pl = total_proceeds - total_cost
    assert round(cp["total_realized_pl"], 2) == round(expected_pl, 2)


def test_partial_sell():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "NOVO", "symbol": "DK",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "NOVO", "symbol": "DK",
         "asset_class": "STOCK", "shares": 4.0, "price": 60.0, "amount": 240.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 1
    op = result["open_positions"][0]
    assert round(op["shares"], 4) == 6.0
    assert len(result["closed_positions"]) == 1
    cp = result["closed_positions"][0]
    expected_pl = 4 * 60 - 4 * 50
    assert round(cp["total_realized_pl"], 2) == expected_pl


def test_fifo_multiple_lots():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "S&P", "symbol": "SP",
         "asset_class": "FUND", "shares": 10.0, "price": 100.0, "amount": -1000.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-15", tz="UTC"), "tx_type": "BUY", "name": "S&P", "symbol": "SP",
         "asset_class": "FUND", "shares": 10.0, "price": 120.0, "amount": -1200.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "S&P", "symbol": "SP",
         "asset_class": "FUND", "shares": 15.0, "price": 130.0, "amount": 1950.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 1
    op = result["open_positions"][0]
    assert round(op["shares"], 4) == 5.0
    cp = result["closed_positions"][0]
    cost_first10 = 10 * 100
    cost_next5 = 5 * 120
    proceeds = 15 * 130
    expected_pl = proceeds - (cost_first10 + cost_next5)
    assert round(cp["total_realized_pl"], 2) == expected_pl


def test_cash_flow():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "DEPOSIT", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 1000.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-15", tz="UTC"), "tx_type": "DIVIDEND", "name": "ASML", "symbol": "NL",
         "asset_class": "STOCK", "shares": 0.0, "price": 0.0, "amount": 50.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "INTEREST", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 5.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    cf = result["cash_flow"]
    assert len(cf) >= 2
    jun = [c for c in cf if c["month"] == "2025-06"]
    assert len(jun) == 1
    assert jun[0]["deposit"] == 1000.0
    assert jun[0]["dividend"] == 50.0
    jul = [c for c in cf if c["month"] == "2025-07"]
    assert len(jul) == 1
    assert jul[0]["interest"] == 5.0


def test_summary():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "DEPOSIT", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 2000.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-02", tz="UTC"), "tx_type": "BUY", "name": "S&P", "symbol": "SP",
         "asset_class": "FUND", "shares": 5.0, "price": 200.0, "amount": -1000.0, "fee": 2.0, "tax": 0.0},
    ])
    result = run_engine(df)
    s = result["summary"]
    assert s["total_deposits"] == 2000.0
    assert s["total_invested"] == 1000.0


def test_knocked_buy_generates_negative_pl():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "TURBO", "symbol": "TURBO",
         "asset_class": "DERIVATIVE", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 2.0, "tax": 0.0,
         "knocked": True},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 0
    assert len(result["closed_positions"]) == 1
    cp = result["closed_positions"][0]
    expected_pl = -(10 * 50 + 2)
    assert round(cp["total_realized_pl"], 2) == round(expected_pl, 2)
    assert cp["total_shares_sold"] == 10.0
    # Monthly PL should reflect the loss
    assert len(result["monthly_pl"]) == 1
    assert result["monthly_pl"][0]["realized_pl"] == round(expected_pl, 2)


def test_knocked_buy_with_other_lots():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "TURBO", "symbol": "TURBO",
         "asset_class": "DERIVATIVE", "shares": 5.0, "price": 100.0, "amount": -500.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-15", tz="UTC"), "tx_type": "BUY", "name": "TURBO", "symbol": "TURBO",
         "asset_class": "DERIVATIVE", "shares": 3.0, "price": 80.0, "amount": -240.0, "fee": 0.0, "tax": 0.0,
         "knocked": True},
    ])
    result = run_engine(df)
    # Only the non-knocked lot remains open
    assert len(result["open_positions"]) == 1
    op = result["open_positions"][0]
    assert round(op["shares"], 4) == 5.0
    # Knocked lot generated a loss
    assert len(result["closed_positions"]) == 1
    cp = result["closed_positions"][0]
    expected_pl = -(3 * 80)
    assert round(cp["total_realized_pl"], 2) == expected_pl


def test_round_trip():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 55.0, "amount": 550.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-08-01", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 5.0, "price": 60.0, "amount": -300.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 1
    assert round(result["open_positions"][0]["shares"], 4) == 5.0
    assert len(result["closed_positions"]) == 1
    assert round(result["closed_positions"][0]["total_realized_pl"], 2) == 50.0

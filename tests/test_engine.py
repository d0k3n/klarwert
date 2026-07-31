import pandas as pd
from portfolio.engine import run_engine, auto_detect_knocked, compute_derivative_executions


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
    expected_pl = total_proceeds - total_cost - 1
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


def test_auto_detect_total_ko():
    df = _make_df([
        {"asset_class": "DERIVATIVE", "type": "BUY", "tx_type": "BUY", "symbol": "DE001",
         "shares": 1352.0, "transaction_id": "tx1", "datetime": pd.Timestamp("2025-06-01", tz="UTC")},
        {"asset_class": "DERIVATIVE", "type": "WARRANT_EXERCISE", "tx_type": "SELL", "symbol": "DE001",
         "shares": 1352.0, "transaction_id": "tx2", "datetime": pd.Timestamp("2025-06-15", tz="UTC")},
    ])
    result = auto_detect_knocked(df)
    assert result == {"tx1"}


def test_auto_detect_hybrid_ko():
    df = _make_df([
        {"asset_class": "DERIVATIVE", "type": "BUY", "tx_type": "BUY", "symbol": "DE002",
         "shares": 1000.0, "transaction_id": "tx1", "datetime": pd.Timestamp("2025-06-01", tz="UTC")},
        {"asset_class": "DERIVATIVE", "type": "BUY", "tx_type": "BUY", "symbol": "DE002",
         "shares": 1000.0, "transaction_id": "tx2", "datetime": pd.Timestamp("2025-06-05", tz="UTC")},
        {"asset_class": "DERIVATIVE", "type": "BUY", "tx_type": "BUY", "symbol": "DE002",
         "shares": 1000.0, "transaction_id": "tx3", "datetime": pd.Timestamp("2025-06-10", tz="UTC")},
        {"asset_class": "DERIVATIVE", "type": "SELL", "tx_type": "SELL", "symbol": "DE002",
         "shares": 500.0, "transaction_id": "tx4", "datetime": pd.Timestamp("2025-06-12", tz="UTC")},
        {"asset_class": "DERIVATIVE", "type": "WARRANT_EXERCISE", "tx_type": "SELL", "symbol": "DE002",
         "shares": 2500.0, "transaction_id": "tx5", "datetime": pd.Timestamp("2025-06-15", tz="UTC")},
    ])
    result = auto_detect_knocked(df)
    # tx1, tx2, tx3 bought = 3000; tx4 sold 500; remaining 2500 matches WE 2500
    assert result == {"tx1", "tx2", "tx3"}


def test_auto_detect_no_we():
    df = _make_df([
        {"asset_class": "DERIVATIVE", "type": "BUY", "tx_type": "BUY", "symbol": "DE003",
         "shares": 1000.0, "transaction_id": "tx1", "datetime": pd.Timestamp("2025-06-01", tz="UTC")},
    ])
    result = auto_detect_knocked(df)
    assert result == set()


def test_auto_detect_all_sold_regular():
    df = _make_df([
        {"asset_class": "DERIVATIVE", "type": "BUY", "tx_type": "BUY", "symbol": "DE004",
         "shares": 1000.0, "transaction_id": "tx1", "datetime": pd.Timestamp("2025-06-01", tz="UTC")},
        {"asset_class": "DERIVATIVE", "type": "SELL", "tx_type": "SELL", "symbol": "DE004",
         "shares": 1000.0, "transaction_id": "tx2", "datetime": pd.Timestamp("2025-06-15", tz="UTC")},
    ])
    result = auto_detect_knocked(df)
    assert result == set()


def test_auto_detect_non_derivative_ignored():
    df = _make_df([
        {"asset_class": "STOCK", "type": "BUY", "tx_type": "BUY", "symbol": "DE005",
         "shares": 100.0, "transaction_id": "tx1", "datetime": pd.Timestamp("2025-06-01", tz="UTC")},
        {"asset_class": "STOCK", "type": "WARRANT_EXERCISE", "tx_type": "SELL", "symbol": "DE005",
         "shares": 100.0, "transaction_id": "tx2", "datetime": pd.Timestamp("2025-06-15", tz="UTC")},
    ])
    result = auto_detect_knocked(df)
    assert result == set()


def test_auto_detect_shares_dont_match():
    df = _make_df([
        {"asset_class": "DERIVATIVE", "type": "BUY", "tx_type": "BUY", "symbol": "DE006",
         "shares": 1000.0, "transaction_id": "tx1", "datetime": pd.Timestamp("2025-06-01", tz="UTC")},
        {"asset_class": "DERIVATIVE", "type": "WARRANT_EXERCISE", "tx_type": "SELL", "symbol": "DE006",
         "shares": 999.0, "transaction_id": "tx2", "datetime": pd.Timestamp("2025-06-15", tz="UTC")},
    ])
    result = auto_detect_knocked(df)
    assert result == set()


def test_knocked_warrant_with_tilg_discounts_pl():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "WARRANT X", "symbol": "DE007",
         "asset_class": "DERIVATIVE", "shares": 100.0, "price": 5.0, "amount": -500.0, "fee": 2.0, "tax": 0.0,
         "knocked": True},
        {"datetime": pd.Timestamp("2025-06-20", tz="UTC"), "tx_type": "TILG", "name": "WARRANT X", "symbol": "DE007",
         "asset_class": "DERIVATIVE", "shares": 0.0, "price": 0.0, "amount": 300.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["closed_positions"]) == 1
    cp = result["closed_positions"][0]
    ko_loss = -(100 * 5 + 2)
    tilg_return = 300.0
    expected_pl = ko_loss + tilg_return
    assert round(cp["total_realized_pl"], 2) == round(expected_pl, 2), \
        f"Expected {expected_pl}, got {cp['total_realized_pl']}"
    # TILG should also be in monthly PL (same month, combined)
    assert len(result["monthly_pl"]) == 1
    assert result["monthly_pl"][0]["month"] == "2025-06"
    assert round(result["monthly_pl"][0]["realized_pl"], 2) == round(expected_pl, 2), \
        f"Expected monthly PL {expected_pl}, got {result['monthly_pl'][0]['realized_pl']}"


def test_sell_fee_deducted_from_realized_pl():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 600.0, "fee": 2.0, "tax": 0.0},
    ])
    result = run_engine(df)
    cp = result["closed_positions"][0]
    expected_pl = 10 * 60 - 10 * 50 - 2
    assert round(cp["total_realized_pl"], 2) == round(expected_pl, 2)


def test_buy_tax_included_in_cost_basis():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 1.0, "tax": 5.0},
    ])
    result = run_engine(df)
    op = result["open_positions"][0]
    expected_cost = 10 * 50 + 1 + 5
    assert round(op["total_cost"], 2) == round(expected_cost, 2)
    assert round(op["average_cost"], 4) == round(expected_cost / 10, 4)


def test_buy_tax_in_realized_pl_on_sell():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 0.0, "tax": 5.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 600.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    cp = result["closed_positions"][0]
    expected_pl = 10 * 60 - (10 * 50 + 5)
    assert round(cp["total_realized_pl"], 2) == round(expected_pl, 2)


def test_sell_tax_deducted_from_realized_pl():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 600.0, "fee": 0.0, "tax": 3.0},
    ])
    result = run_engine(df)
    cp = result["closed_positions"][0]
    expected_pl = 10 * 60 - 10 * 50 - 3
    assert round(cp["total_realized_pl"], 2) == round(expected_pl, 2)


def test_knocked_buy_tax_included_in_loss():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "TURBO", "symbol": "TURBO",
         "asset_class": "DERIVATIVE", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 2.0, "tax": 1.0,
         "knocked": True},
    ])
    result = run_engine(df)
    cp = result["closed_positions"][0]
    expected_pl = -(10 * 50 + 2 + 1)
    assert round(cp["total_realized_pl"], 2) == round(expected_pl, 2)


def test_saveback_in_summary():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "DEPOSIT", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 1000.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-02", tz="UTC"), "tx_type": "SAVEBACK", "name": "S&P", "symbol": "IE",
         "asset_class": "FUND", "shares": 0.0, "price": 0.0, "amount": 5.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    s = result["summary"]
    assert s["total_saveback"] == 5.0


def test_total_income_in_summary():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "DEPOSIT", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 1000.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-02", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 600.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-06", tz="UTC"), "tx_type": "DIVIDEND", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 0.0, "price": 0.0, "amount": 20.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "INTEREST", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 3.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-02", tz="UTC"), "tx_type": "SAVEBACK", "name": "X", "symbol": "X",
         "asset_class": "FUND", "shares": 0.0, "price": 0.0, "amount": 2.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    s = result["summary"]
    assert s["total_realized_pl"] == 100.0
    assert s["total_dividends"] == 20.0
    assert s["total_interest"] == 3.0
    assert s["total_saveback"] == 2.0
    assert s["total_income"] == round(100.0 + 20.0 + 3.0 + 2.0, 2)


def test_warrant_exercise_no_duplicate_shares_sold():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "TURBO", "symbol": "TURBO",
         "asset_class": "DERIVATIVE", "shares": 100.0, "price": 1.5, "amount": -150.0, "fee": 1.0, "tax": 0.0,
         "knocked": True},
        {"datetime": pd.Timestamp("2025-06-15", tz="UTC"), "tx_type": "SELL", "name": "TURBO", "symbol": "TURBO",
         "asset_class": "DERIVATIVE", "shares": 100.0, "price": 0.0, "amount": 0.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    cp = result["closed_positions"][0]
    assert cp["total_shares_sold"] == 100.0
    assert cp["closed_lots"] == 1


def test_knocked_loss_booked_at_exercise_month():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-01-15", tz="UTC"), "type": "BUY", "tx_type": "BUY",
         "name": "TURBO", "symbol": "TURBO", "asset_class": "DERIVATIVE",
         "shares": 100.0, "price": 5.0, "amount": -500.0, "fee": 2.0, "tax": 0.0,
         "transaction_id": "b1", "knocked": True},
        {"datetime": pd.Timestamp("2025-03-06", tz="UTC"), "type": "WARRANT_EXERCISE", "tx_type": "SELL",
         "name": "TURBO", "symbol": "TURBO", "asset_class": "DERIVATIVE",
         "shares": 100.0, "price": 0.0, "amount": 0.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "we1"},
    ])
    result = run_engine(df)
    assert len(result["monthly_pl"]) == 1
    assert result["monthly_pl"][0]["month"] == "2025-03"
    assert result["monthly_pl"][0]["realized_pl"] == round(-(100 * 5 + 2), 2)


def test_knocked_loss_cross_year_goes_to_disposal_year():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-12-20", tz="UTC"), "type": "BUY", "tx_type": "BUY",
         "name": "TURBO", "symbol": "TURBO", "asset_class": "DERIVATIVE",
         "shares": 100.0, "price": 5.0, "amount": -500.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "b1", "knocked": True},
        {"datetime": pd.Timestamp("2026-01-10", tz="UTC"), "type": "WARRANT_EXERCISE", "tx_type": "SELL",
         "name": "TURBO", "symbol": "TURBO", "asset_class": "DERIVATIVE",
         "shares": 100.0, "price": 0.0, "amount": 0.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "we1"},
    ])
    result = run_engine(df)
    assert result["monthly_pl"][0]["month"] == "2026-01"


def test_tilg_consumes_open_lots():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "W", "symbol": "DE100",
         "asset_class": "DERIVATIVE", "shares": 100.0, "price": 5.0, "amount": -500.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-20", tz="UTC"), "tx_type": "TILG", "name": "W", "symbol": "DE100",
         "asset_class": "DERIVATIVE", "shares": 0.0, "price": 0.0, "amount": 300.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 0
    assert len(result["closed_positions"]) == 1
    cp = result["closed_positions"][0]
    assert round(cp["total_realized_pl"], 2) == round(300.0 - 500.0, 2)
    assert cp["total_shares_sold"] == 100.0
    assert result["monthly_pl"] == [{"month": "2025-06", "realized_pl": -200.0}]


def test_tilg_does_not_touch_lots_bought_after():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "W", "symbol": "DE101",
         "asset_class": "DERIVATIVE", "shares": 100.0, "price": 5.0, "amount": -500.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-20", tz="UTC"), "tx_type": "TILG", "name": "W", "symbol": "DE101",
         "asset_class": "DERIVATIVE", "shares": 0.0, "price": 0.0, "amount": 300.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-25", tz="UTC"), "tx_type": "BUY", "name": "W", "symbol": "DE101",
         "asset_class": "DERIVATIVE", "shares": 50.0, "price": 6.0, "amount": -300.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 1
    op = result["open_positions"][0]
    assert round(op["shares"], 4) == 50.0
    assert round(op["total_cost"], 2) == 300.0
    assert round(result["closed_positions"][0]["total_realized_pl"], 2) == -200.0


def test_tilg_only_isin_appears_in_closed_positions():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-20", tz="UTC"), "tx_type": "TILG", "name": "ORPHAN", "symbol": "DE102",
         "asset_class": "DERIVATIVE", "shares": 0.0, "price": 0.0, "amount": 25.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["closed_positions"]) == 1
    assert result["closed_positions"][0]["total_realized_pl"] == 25.0
    assert result["monthly_pl"] == [{"month": "2025-06", "realized_pl": 25.0}]


def test_unmatched_sell_creates_short_position():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 600.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 1
    op = result["open_positions"][0]
    assert round(op["shares"], 4) == -10.0
    assert round(op["total_cost"], 2) == -600.0
    assert len(result["closed_positions"]) == 0
    assert result["summary"]["total_realized_pl"] == 0.0


def test_short_covered_by_later_buy():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 600.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 0
    assert len(result["closed_positions"]) == 1
    cp = result["closed_positions"][0]
    assert round(cp["total_realized_pl"], 2) == 100.0
    assert cp["total_shares_sold"] == 10.0
    assert result["monthly_pl"] == [{"month": "2025-07", "realized_pl": 100.0}]


def test_zero_price_unmatched_sell_leaves_no_short():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "T", "symbol": "T",
         "asset_class": "DERIVATIVE", "shares": 100.0, "price": 1.5, "amount": -150.0, "fee": 1.0, "tax": 0.0,
         "knocked": True},
        {"datetime": pd.Timestamp("2025-06-15", tz="UTC"), "tx_type": "SELL", "name": "T", "symbol": "T",
         "asset_class": "DERIVATIVE", "shares": 100.0, "price": 0.0, "amount": 0.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 0


def test_dust_lot_cost_booked_on_sell():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0005, "price": 100.0, "amount": -1000.05, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 100.0, "amount": 1000.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 0
    cp = result["closed_positions"][0]
    assert round(cp["total_realized_pl"], 2) == -0.05


def test_leftover_dust_written_off_at_last_event():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 0.0005, "price": 1000.0, "amount": -0.5, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["open_positions"]) == 0
    assert len(result["closed_positions"]) == 1
    assert round(result["closed_positions"][0]["total_realized_pl"], 2) == -0.5
    assert result["monthly_pl"] == [{"month": "2025-06", "realized_pl": -0.5}]


def test_dividend_withholding_tax_fields():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "ABC", "symbol": "US1",
         "asset_class": "STOCK", "shares": 6.0, "price": 100.0, "amount": -600.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "DIVIDEND", "name": "ABC", "symbol": "US1",
         "asset_class": "STOCK", "shares": 6.0, "price": 0.0, "amount": 1.14, "fee": 0.0, "tax": -0.17},
    ])
    result = run_engine(df)
    p = result["products"][0]
    assert p["total_dividends"] == 1.14
    assert p["total_dividend_tax"] == 0.17
    assert p["total_dividends_net"] == 0.97
    s = result["summary"]
    assert s["total_dividends"] == 1.14
    assert s["total_dividend_tax"] == 0.17
    assert s["total_dividends_net"] == 0.97


def test_dividend_for_untraded_isin_creates_product():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "DIVIDEND", "name": "ORPHAN", "symbol": "XX",
         "asset_class": "STOCK", "shares": 0.0, "price": 0.0, "amount": 5.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert len(result["products"]) == 1
    p = result["products"][0]
    assert p["isin"] == "XX"
    assert p["total_dividends"] == 5.0
    assert p["total_trades"] == 0


def test_negative_dividend_adjustment_reduces_total():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "ABC", "symbol": "US1",
         "asset_class": "STOCK", "shares": 6.0, "price": 100.0, "amount": -600.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "DIVIDEND", "name": "ABC", "symbol": "US1",
         "asset_class": "STOCK", "shares": 0.0, "price": 0.0, "amount": 10.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-08-01", tz="UTC"), "tx_type": "DIVIDEND", "name": "ABC", "symbol": "US1",
         "asset_class": "STOCK", "shares": 0.0, "price": 0.0, "amount": -2.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    assert result["summary"]["total_dividends"] == 8.0


def test_derivative_executions_include_buy_tax():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "type": "BUY", "tx_type": "BUY",
         "name": "TURBO", "symbol": "TURBO", "asset_class": "DERIVATIVE",
         "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 2.0, "tax": 1.0,
         "transaction_id": "b1", "knocked": True},
    ])
    entries = compute_derivative_executions(df, {"b1"})
    assert len(entries) == 1
    e = entries[0]
    assert e["ko_loss"] == -500.0
    assert e["ko_fees"] == -2.0
    assert e["ko_tax"] == -1.0
    assert e["ko_total"] == -503.0
    eng = run_engine(df)
    assert round(eng["closed_positions"][0]["total_realized_pl"], 2) == e["ko_total"]


def test_reconciliation_balances_on_full_cycle():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "DEPOSIT", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 2000.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-02", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 1.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 600.0, "fee": 1.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-06", tz="UTC"), "tx_type": "DIVIDEND", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 0.0, "price": 0.0, "amount": 20.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-10", tz="UTC"), "tx_type": "CARD", "name": "SHOP", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": -30.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-15", tz="UTC"), "tx_type": "INTEREST", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 5.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    rec = result["summary"]["reconciliation"]
    assert rec["net_deposits"] == 2000.0
    assert rec["realized_pl"] == 98.0
    assert rec["cash_balance"] == 2093.0
    assert rec["open_positions_cost"] == 0.0
    assert rec["card_spending"] == 30.0
    assert abs(rec["difference"]) <= 0.01


def test_reconciliation_captures_standalone_fee_column():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "DEPOSIT", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 2000.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-02", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -500.0, "fee": 1.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-03", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 600.0, "fee": 1.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-15", tz="UTC"), "tx_type": "FEE", "name": "TR", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 0.0, "fee": -5.0, "tax": 0.0},
    ])
    result = run_engine(df)
    rec = result["summary"]["reconciliation"]
    assert rec["cash_balance"] == 2093.0
    assert rec["fees"] == 5.0
    assert abs(rec["difference"]) <= 0.01

import pandas as pd
from portfolio.engine import run_engine
from portfolio.tax_report import build_tax_report


def _df():
    return pd.DataFrame([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "type": "BUY", "tx_type": "BUY",
         "name": "X", "symbol": "X", "asset_class": "STOCK", "shares": 10.0, "price": 50.0,
         "amount": -501.0, "fee": 1.0, "tax": 0.0, "transaction_id": "b1"},
        {"datetime": pd.Timestamp("2026-02-01", tz="UTC"), "type": "SELL", "tx_type": "SELL",
         "name": "X", "symbol": "X", "asset_class": "STOCK", "shares": 10.0, "price": 60.0,
         "amount": 599.0, "fee": 1.0, "tax": 0.0, "transaction_id": "s1"},
        {"datetime": pd.Timestamp("2026-03-01", tz="UTC"), "type": "DIVIDEND", "tx_type": "DIVIDEND",
         "name": "X", "symbol": "X", "asset_class": "STOCK", "shares": 0.0, "price": 0.0,
         "amount": 20.0, "fee": 0.0, "tax": -3.0, "transaction_id": "d1",
         "currency": "EUR", "original_currency": "USD"},
        {"datetime": pd.Timestamp("2026-04-01", tz="UTC"), "type": "INTEREST_PAYMENT", "tx_type": "INTEREST",
         "name": "", "symbol": "", "asset_class": "", "shares": 0.0, "price": 0.0,
         "amount": 5.0, "fee": 0.0, "tax": 0.0, "transaction_id": "i1",
         "currency": "EUR", "original_currency": ""},
    ])


def test_year_filtering_and_disposal_aggregation():
    df = _df()
    result = run_engine(df)
    report = build_tax_report(df, result["lot_matches"], 2026)
    assert report["year"] == 2026
    assert len(report["disposals"]) == 1
    d = report["disposals"][0]
    assert d["date"].startswith("2026-02-01")
    assert d["shares"] == 10.0
    assert d["proceeds"] == 600.0
    assert d["cost_basis"] == 501.0
    assert d["fees"] == 1.0
    assert d["gain"] == 98.0
    assert d["acquired"].startswith("2025-06-01")
    assert report["disposal_totals"]["gain"] == 98.0


def test_2025_has_no_disposals():
    df = _df()
    result = run_engine(df)
    report = build_tax_report(df, result["lot_matches"], 2025)
    assert report["disposals"] == []
    assert report["disposal_totals"]["gain"] == 0.0


def test_dividends_and_income_totals():
    df = _df()
    result = run_engine(df)
    report = build_tax_report(df, result["lot_matches"], 2026)
    assert len(report["dividends"]) == 1
    div = report["dividends"][0]
    assert div["gross"] == 20.0
    assert div["wht"] == 3.0
    assert div["net"] == 17.0
    assert div["currency"] == "USD"
    assert report["dividend_totals"] == {"gross": 20.0, "wht": 3.0, "net": 17.0}
    assert report["interest"] == 5.0
    assert report["saveback"] == 0.0

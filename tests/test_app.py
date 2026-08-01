import io
import pandas as pd
import pytest

import app as app_module


def _df():
    return pd.DataFrame([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "type": "TRANSFER_INSTANT_INBOUND",
         "tx_type": "DEPOSIT", "name": "", "symbol": "", "asset_class": "",
         "shares": 0.0, "price": 0.0, "amount": 1000.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "d1"},
    ])


def _card_df():
    return pd.DataFrame([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "type": "CARD_TRANSACTION",
         "tx_type": "CARD", "name": "ISLA MADRID", "symbol": "", "asset_class": "",
         "shares": 0.0, "price": 0.0, "amount": -10.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "c1", "description": "", "mcc_code": ""},
        {"datetime": pd.Timestamp("2025-06-02", tz="UTC"), "type": "CARD_TRANSACTION",
         "tx_type": "CARD", "name": "ISLA MADRID", "symbol": "", "asset_class": "",
         "shares": 0.0, "price": 0.0, "amount": -5.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "c2", "description": "", "mcc_code": ""},
        {"datetime": pd.Timestamp("2025-06-03", tz="UTC"), "type": "CARD_TRANSACTION",
         "tx_type": "CARD", "name": "INTERMARCHE", "symbol": "", "asset_class": "",
         "shares": 0.0, "price": 0.0, "amount": -50.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "c3", "description": "", "mcc_code": "5411"},
    ])


@pytest.fixture(autouse=True)
def restore_state():
    old_df = app_module.df
    app_module.invalidate_cache()
    yield
    app_module.df = old_df
    app_module.invalidate_cache()


def test_compute_data_caches_result(monkeypatch):
    calls = {"n": 0}
    real = app_module.run_engine

    def counting(d):
        calls["n"] += 1
        return real(d)

    monkeypatch.setattr(app_module, "run_engine", counting)
    app_module.df = _df()
    app_module.compute_data(set())
    app_module.compute_data(set())
    assert calls["n"] == 1
    app_module.compute_data({"other-ids"})
    assert calls["n"] == 2


def test_upload_parses_without_temp_file(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CSV_PATH", tmp_path / "transactions.csv")
    header = (
        "datetime,date,account_type,category,type,asset_class,name,symbol,"
        "shares,price,amount,fee,tax,currency,original_amount,"
        "original_currency,fx_rate,description,transaction_id,"
        "counterparty_name,counterparty_iban,payment_reference,mcc_code\n"
    )
    row = (
        "2025-05-27T11:16:23.775580Z,2025-05-27,DEFAULT,CASH,TRANSFER_INSTANT_INBOUND,,,,,,1000.00,,EUR,,,,Incoming,up1,,,,\n"
    )
    client = app_module.app.test_client()
    resp = client.post("/api/upload", data={"file": (io.BytesIO((header + row).encode("utf-8")), "t.csv")})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert app_module.df is not None
    assert len(app_module.df) == 1


def test_analysis_endpoints_do_not_500():
    app_module.df = _df()
    app_module.invalidate_cache()
    client = app_module.app.test_client()
    for endpoint in [
        "/api/performance",
        "/api/income",
        "/api/spending",
        "/api/valued_positions",
        "/api/tax_report?year=2025",
        "/api/lot_matches",
        "/api/summary",
    ]:
        resp = client.get(endpoint)
        assert resp.status_code == 200, f"{endpoint} returned {resp.status_code}"


def test_refresh_prices_endpoint_merges_and_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "PRICES_PATH", tmp_path / "prices.json")
    monkeypatch.setattr(app_module, "TICKERS_PATH", tmp_path / "tickers.json")
    app_module.save_prices({"A": {"price": 5.0, "source": "manual"}})

    fake = lambda *a, **k: {
        "prices": {"B": {"price": 12.0, "source": "yahoo"}},
        "tickers": {"B": "BB"},
        "skipped": [{"isin": "A", "reason": "manual"}],
    }
    monkeypatch.setattr(app_module, "refresh_prices", fake)

    app_module.df = _df()
    app_module.invalidate_cache()
    client = app_module.app.test_client()
    resp = client.post("/api/refresh_prices")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["prices"]["B"]["source"] == "yahoo"
    assert body["skipped"][0]["reason"] == "manual"
    # manual entry preserved, yahoo entry persisted to disk
    saved = app_module.load_prices()
    assert saved["A"] == {"price": 5.0, "source": "manual"}
    assert saved["B"] == {"price": 12.0, "source": "yahoo"}
    assert app_module.load_tickers() == {"B": "BB"}


def test_card_rules_api_list_upsert_delete(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "RULES_PATH", tmp_path / "card_rules.json")
    app_module.df = _card_df()
    app_module.invalidate_cache()
    client = app_module.app.test_client()

    body = client.get("/api/card_rules").get_json()
    assert body["rules"] == []
    assert body["uncategorized_vendors"] == [{"name": "ISLA MADRID", "count": 2, "total": 15.0}]

    resp = client.post("/api/card_rules", json={"pattern": "isla", "category": "Education"})
    assert resp.status_code == 200
    assert resp.get_json()["rules"] == [{"pattern": "isla", "category": "Education"}]

    body = client.get("/api/card_rules").get_json()
    assert body["rules"] == [{"pattern": "isla", "category": "Education"}]
    assert body["uncategorized_vendors"] == []

    resp = client.delete("/api/card_rules", json={"pattern": "isla"})
    assert resp.status_code == 200
    assert resp.get_json()["rules"] == []

    body = client.get("/api/card_rules").get_json()
    assert body["uncategorized_vendors"] == [{"name": "ISLA MADRID", "count": 2, "total": 15.0}]


def test_card_rules_post_upserts_same_normalized_pattern(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "RULES_PATH", tmp_path / "card_rules.json")
    client = app_module.app.test_client()
    client.post("/api/card_rules", json={"pattern": "ISLA", "category": "Education"})
    resp = client.post("/api/card_rules", json={"pattern": "isla", "category": "Tuition"})
    assert resp.get_json()["rules"] == [{"pattern": "isla", "category": "Tuition"}]


def test_card_rules_post_requires_pattern_and_category(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "RULES_PATH", tmp_path / "card_rules.json")
    client = app_module.app.test_client()
    assert client.post("/api/card_rules", json={"pattern": "", "category": "Education"}).status_code == 400
    assert client.post("/api/card_rules", json={"pattern": "isla", "category": " "}).status_code == 400


def test_card_transactions_and_spending_reflect_rules(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "RULES_PATH", tmp_path / "card_rules.json")
    app_module.df = _card_df()
    app_module.invalidate_cache()
    client = app_module.app.test_client()
    client.post("/api/card_rules", json={"pattern": "isla", "category": "Education"})

    txns = client.get("/api/card_transactions").get_json()
    assert all(t["category"] == "Education" for t in txns if "ISLA" in t["name"])

    spending = client.get("/api/spending").get_json()
    by_cat = {c["category"]: c["total"] for c in spending["by_category"]}
    assert by_cat["Education"] == 15.0
    assert by_cat["Groceries"] == 50.0

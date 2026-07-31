import pandas as pd
import tempfile
from pathlib import Path

from portfolio.parser import parse_csv


def _make_csv(lines):
    header = (
        "datetime,date,account_type,category,type,asset_class,name,symbol,"
        "shares,price,amount,fee,tax,currency,original_amount,"
        "original_currency,fx_rate,description,transaction_id,"
        "counterparty_name,counterparty_iban,payment_reference,mcc_code"
    )
    content = "\n".join([header] + lines)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        f.write(content)
        return Path(f.name)


def test_parse_buy_trade():
    csv = _make_csv([
        "2025-06-02T14:24:16.757Z,2025-06-02,DEFAULT,TRADING,BUY,FUND,Core S&P 500 USD (Acc),IE00B5BMR087,"
        "0.182315,548.50,-100.00,,,EUR,,,,Savings plan execution,id1,,,,"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["tx_type"] == "BUY"
    assert row["shares"] == 0.182315
    assert row["price"] == 548.50
    assert row["amount"] == -100.00
    assert row["asset_class"] == "FUND"
    assert row["symbol"] == "IE00B5BMR087"


def test_parse_sell_trade():
    csv = _make_csv([
        "2025-07-25T09:04:17.842Z,2025-07-25,DEFAULT,TRADING,SELL,STOCK,Novo-Nordisk (B),DK0062498333,"
        "-69.832405,61.11,4267.46,-1.00,,EUR,,,,Sell trade,id2,,,,"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["tx_type"] == "SELL"
    assert row["shares"] == 69.832405
    assert row["amount"] == 4267.46


def test_parse_deposit():
    csv = _make_csv([
        "2025-05-27T11:16:23.775580Z,2025-05-27,DEFAULT,CASH,TRANSFER_INSTANT_INBOUND,,,,,,1000.00,,EUR,,,,Incoming transfer,id3,,,,"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 1
    assert df.iloc[0]["tx_type"] == "DEPOSIT"


def test_parse_dividend():
    csv = _make_csv([
        "2025-08-06T15:59:12.528155Z,2025-08-06,DEFAULT,CASH,DIVIDEND,STOCK,ASML,NL0010273215,8.184456,,11.13,,EUR,,,,Cash Dividend,id4,,,,"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 1
    assert df.iloc[0]["tx_type"] == "DIVIDEND"


def test_parse_card_transaction():
    csv = _make_csv([
        "2025-05-29T10:10:34.157449Z,2025-05-29,DEFAULT,CASH,CARD_TRANSACTION,,INTERMARCHE,,,,-9.98,,EUR,,,,TR Card Transaction,id5,,,,5411"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 1
    assert df.iloc[0]["tx_type"] == "CARD"


def test_parse_interest():
    csv = _make_csv([
        "2025-06-01T08:38:03.339385Z,2025-06-01,DEFAULT,CASH,INTEREST_PAYMENT,,,,,,0.64,,EUR,,,,Interest payment,id6,,,,"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 1
    assert df.iloc[0]["tx_type"] == "INTEREST"


def test_parse_withdrawal():
    csv = _make_csv([
        "2025-09-24T11:43:23.917166Z,2025-09-24,DEFAULT,CASH,TRANSFER_INSTANT_OUTBOUND,,,,,,-500.00,,EUR,,,,Outgoing transfer,id7,,,,"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 1
    assert df.iloc[0]["tx_type"] == "WITHDRAWAL"


def test_parse_fee():
    csv = _make_csv([
        "2025-08-11T14:49:15.135876Z,2025-08-11,DEFAULT,CASH,CARD_ORDERING_FEE,,,,,,0.000000,-5.00,,EUR,,,,Trade Republic Card,id8,,,,"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 1
    assert df.iloc[0]["tx_type"] == "FEE"


def test_parse_saveback():
    csv = _make_csv([
        "2025-07-02T13:53:16.620142Z,2025-07-02,DEFAULT,CASH,BENEFITS_SAVEBACK,FUND,Core S&P 500 USD (Acc),IE00B5BMR087,,,,2.94,,EUR,,,,Your Saveback payment,id9,,,,"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 1
    assert df.iloc[0]["tx_type"] == "SAVEBACK"


def test_numeric_coercion():
    csv = _make_csv([
        "2025-06-02T14:24:16.757Z,2025-06-02,DEFAULT,TRADING,BUY,FUND,Fund,A,invalid,invalid,-100.00,,EUR,,,,desc,id10,,,,"
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    row = df.iloc[0]
    assert pd.isna(row["shares"])
    assert pd.isna(row["price"])
    assert row["amount"] == -100.00


def test_parse_from_bytesio():
    import io
    header = (
        "datetime,date,account_type,category,type,asset_class,name,symbol,"
        "shares,price,amount,fee,tax,currency,original_amount,"
        "original_currency,fx_rate,description,transaction_id,"
        "counterparty_name,counterparty_iban,payment_reference,mcc_code\n"
    )
    row = (
        "2025-06-02T14:24:16.757Z,2025-06-02,DEFAULT,TRADING,BUY,FUND,Fund,IE00B5BMR087,"
        "0.182315,548.50,-100.00,,,EUR,,,,desc,id100,,,,\n"
    )
    df = parse_csv(io.BytesIO((header + row).encode("utf-8")))
    assert len(df) == 1
    assert df.iloc[0]["tx_type"] == "BUY"


def test_duplicate_transaction_id_dropped():
    csv = _make_csv([
        "2025-05-27T11:16:23.775580Z,2025-05-27,DEFAULT,CASH,TRANSFER_INSTANT_INBOUND,,,,,,1000.00,,,EUR,,,,Incoming,id200,,,,",
        "2025-05-27T11:16:23.775580Z,2025-05-27,DEFAULT,CASH,TRANSFER_INSTANT_INBOUND,,,,,,1000.00,,,EUR,,,,Incoming,id200,,,,",
        "2025-05-28T11:16:23.775580Z,2025-05-28,DEFAULT,CASH,TRANSFER_INSTANT_INBOUND,,,,,,500.00,,,EUR,,,,Incoming,id201,,,,",
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 2


def test_migration_rows_classified_and_balanced(caplog):
    csv = _make_csv([
        "2026-07-17T01:08:54.572Z,2026-07-17,DEFAULT,DELIVERY,MIGRATION,STOCK,Santander,ES0113900J37,-375.0,12.0487,,,,EUR,,,,MIGRATION ES0113900J37,id300,,,,",
        "2026-07-17T01:08:54.581Z,2026-07-17,DEFAULT,DELIVERY,MIGRATION,STOCK,Santander,ES0113900J37,375.0,12.0487,,,,EUR,,,,MIGRATION ES0113900J37,id301,,,,",
    ])
    import logging
    with caplog.at_level(logging.WARNING):
        df = parse_csv(str(csv))
    csv.unlink()
    assert list(df["tx_type"]) == ["MIGRATION", "MIGRATION"]
    # balanced pair: no "Unpaired MIGRATION" warning
    assert not any("Unpaired MIGRATION" in r.message for r in caplog.records)


def test_unpaired_migration_warns(caplog):
    csv = _make_csv([
        "2026-07-17T01:08:54.572Z,2026-07-17,DEFAULT,DELIVERY,MIGRATION,STOCK,Santander,ES0113900J37,375.0,12.0487,,,,EUR,,,,MIGRATION ES0113900J37,id302,,,,",
    ])
    import logging
    with caplog.at_level(logging.WARNING):
        df = parse_csv(str(csv))
    csv.unlink()
    assert df.iloc[0]["tx_type"] == "MIGRATION"
    assert any("Unpaired MIGRATION" in r.message for r in caplog.records)

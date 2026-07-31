import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

TRADING_TYPES = {"BUY", "SELL"}
CASH_TYPES = {
    "TRANSFER_INSTANT_INBOUND": "DEPOSIT",
    "TRANSFER_INSTANT_OUTBOUND": "WITHDRAWAL",
    "CARD_TRANSACTION": "CARD",
    "CARD_TRANSACTION_INTERNATIONAL": "CARD",
    "CARD_ORDERING_FEE": "FEE",
    "DIVIDEND": "DIVIDEND",
    "INTEREST_PAYMENT": "INTEREST",
    "BENEFITS_SAVEBACK": "SAVEBACK",
    "TILG": "TILG",
}
SELL_TYPES = {"WARRANT_EXERCISE"}
OTHER_TYPES = set()


def parse_csv(filepath):
    df = pd.read_csv(filepath, dtype=str)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    numeric_cols = ["shares", "price", "amount", "fee", "tax"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["shares"] = df["shares"].abs()
    string_cols = df.select_dtypes(include=["str"]).columns
    df[string_cols] = df[string_cols].fillna("")

    df["tx_type"] = df.apply(_classify_row, axis=1)
    return df


def _classify_row(row):
    if row["category"] == "TRADING" and row["type"] in TRADING_TYPES:
        return row["type"]
    if row["type"] in SELL_TYPES:
        return "SELL"
    if row["type"] in CASH_TYPES:
        return CASH_TYPES[row["type"]]
    logger.warning("Unrecognized row type=%s category=%s", row["type"], row["category"])
    return "OTHER"

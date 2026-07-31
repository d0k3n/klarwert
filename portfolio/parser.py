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
DELIVERY_TYPES = {"MIGRATION": "MIGRATION"}
SELL_TYPES = {"WARRANT_EXERCISE"}
OTHER_TYPES = set()


def parse_csv(filepath):
    """Parse a Trade Republic CSV export.

    `filepath` may be a path string or a file-like object (e.g. io.BytesIO).
    """
    df = pd.read_csv(filepath, dtype=str)
    df = _drop_duplicates(df)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    numeric_cols = ["shares", "price", "amount", "fee", "tax"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    _check_migration_balance(df)

    df["shares"] = df["shares"].abs()
    string_cols = df.select_dtypes(include=["str"]).columns
    df[string_cols] = df[string_cols].fillna("")

    df["tx_type"] = df.apply(_classify_row, axis=1)
    return df


def _drop_duplicates(df):
    if "transaction_id" not in df.columns:
        return df
    has_id = df["transaction_id"].fillna("").ne("")
    dupes = has_id & df.duplicated(subset="transaction_id", keep="first")
    if dupes.any():
        logger.warning("Dropped %d duplicate rows by transaction_id", int(dupes.sum()))
        df = df[~dupes]
    return df


def _check_migration_balance(df):
    mig = df[df["type"] == "MIGRATION"]
    if mig.empty:
        return
    balance = mig.groupby("symbol")["shares"].sum()
    unbalanced = balance[balance.abs() > 0.001]
    if not unbalanced.empty:
        logger.warning(
            "Unpaired MIGRATION rows (net shares != 0): %s", unbalanced.to_dict()
        )


def _classify_row(row):
    if row["category"] == "TRADING" and row["type"] in TRADING_TYPES:
        return row["type"]
    if row["type"] in SELL_TYPES:
        return "SELL"
    if row["type"] in CASH_TYPES:
        return CASH_TYPES[row["type"]]
    if row["type"] in DELIVERY_TYPES:
        return DELIVERY_TYPES[row["type"]]
    logger.warning("Unrecognized row type=%s category=%s", row["type"], row["category"])
    return "OTHER"

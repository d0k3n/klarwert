import math
import pandas as pd


def _isna(val):
    return val is None or (isinstance(val, float) and math.isnan(val))


def build_tax_report(df, lot_matches, year):
    fee_by_sell = {}
    for _, row in df[df["tx_type"] == "SELL"].iterrows():
        sid = str(row.get("transaction_id", "") or "")
        fee = abs(row["fee"]) if not _isna(row["fee"]) else 0.0
        tax = abs(row["tax"]) if not _isna(row["tax"]) else 0.0
        fee_by_sell[sid] = fee + tax

    disposals = {}
    for m in lot_matches:
        dt = pd.Timestamp(m["sell_datetime"])
        if dt.year != year:
            continue
        key = (m["sell_id"], m["sell_datetime"], m["isin"])
        d = disposals.setdefault(key, {
            "date": m["sell_datetime"][:10],
            "name": m["name"],
            "isin": m["isin"],
            "shares": 0.0,
            "proceeds": 0.0,
            "cost_basis": 0.0,
            "fees": fee_by_sell.get(m["sell_id"], 0.0),
            "acquired_dates": set(),
        })
        d["shares"] += m["shares"]
        d["proceeds"] += m["proceeds"]
        d["cost_basis"] += m["cost_basis"]
        if m["lot_datetime"]:
            d["acquired_dates"].add(m["lot_datetime"][:10])

    disposal_list = []
    for d in disposals.values():
        disposal_list.append({
            "date": d["date"],
            "name": d["name"],
            "isin": d["isin"],
            "shares": round(d["shares"], 6),
            "proceeds": round(d["proceeds"], 2),
            "cost_basis": round(d["cost_basis"], 2),
            "fees": round(d["fees"], 2),
            "gain": round(d["proceeds"] - d["cost_basis"] - d["fees"], 2),
            "acquired": ", ".join(sorted(d["acquired_dates"])),
        })
    disposal_list.sort(key=lambda x: x["date"])

    totals = {
        "proceeds": round(sum(d["proceeds"] for d in disposal_list), 2),
        "cost_basis": round(sum(d["cost_basis"] for d in disposal_list), 2),
        "fees": round(sum(d["fees"] for d in disposal_list), 2),
        "gain": round(sum(d["gain"] for d in disposal_list), 2),
    }

    dividends = []
    for _, row in df[df["tx_type"] == "DIVIDEND"].iterrows():
        if row["datetime"].year != year:
            continue
        gross = row["amount"] if not _isna(row["amount"]) else 0.0
        wht = abs(row["tax"]) if not _isna(row["tax"]) else 0.0
        currency = row.get("original_currency") or row.get("currency") or ""
        dividends.append({
            "date": row["datetime"].isoformat()[:10],
            "name": row["name"],
            "isin": row["symbol"],
            "gross": round(gross, 2),
            "wht": round(wht, 2),
            "net": round(gross - wht, 2),
            "currency": currency,
        })
    dividends.sort(key=lambda x: x["date"])
    div_totals = {
        "gross": round(sum(d["gross"] for d in dividends), 2),
        "wht": round(sum(d["wht"] for d in dividends), 2),
        "net": round(sum(d["net"] for d in dividends), 2),
    }

    year_mask = df["datetime"].dt.year == year
    interest = df[(df["tx_type"] == "INTEREST") & year_mask]["amount"].sum()
    saveback = df[(df["tx_type"] == "SAVEBACK") & year_mask]["amount"].sum()

    return {
        "year": year,
        "disposals": disposal_list,
        "disposal_totals": totals,
        "dividends": dividends,
        "dividend_totals": div_totals,
        "interest": round(interest, 2),
        "saveback": round(saveback, 2),
    }

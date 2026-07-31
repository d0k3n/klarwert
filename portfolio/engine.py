import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Lot:
    id: int
    shares: float
    price: float
    total_cost: float


def run_engine(df):
    trades = df[df["tx_type"].isin({"BUY", "SELL"})].sort_values("datetime").copy()
    cash_rows = df[~df["tx_type"].isin({"BUY", "SELL"})].copy()

    we_dates = {}
    if "type" in df.columns:
        for _, r in df[df["type"] == "WARRANT_EXERCISE"].iterrows():
            d = r["datetime"]
            if r["symbol"] not in we_dates or d < we_dates[r["symbol"]]:
                we_dates[r["symbol"]] = d

    by_isin = defaultdict(list)
    for _, row in trades.iterrows():
        by_isin[row["symbol"]].append(row)

    monthly_pl = defaultdict(float)
    per_product = {}

    open_positions = []
    closed_positions = defaultdict(lambda: {
        "isin": "", "name": "", "total_realized_pl": 0.0,
        "closed_lots": 0, "total_shares_sold": 0.0,
    })

    for isin, rows in by_isin.items():
        name = rows[0]["name"]
        total_invested = 0.0
        total_fees = 0.0
        total_trades = 0
        lot_id_gen = iter(range(1, 10**9))
        open_lots = []

        for row in rows:
            shares = row["shares"]
            price = abs(row["price"]) if not _isna(row["price"]) else 0.0
            fee = abs(row["fee"]) if not _isna(row["fee"]) else 0.0
            tax = abs(row["tax"]) if not _isna(row["tax"]) else 0.0
            total_cost = shares * price + fee + tax

            if row["tx_type"] == "BUY":
                total_invested += shares * price
                total_fees += fee
                total_trades += 1
                lot = Lot(id=next(lot_id_gen), shares=shares, price=price, total_cost=total_cost)

                if row.get("knocked") is True:
                    realized_pl = -lot.total_cost
                    ko_dt = we_dates.get(isin, row["datetime"])
                    month = ko_dt.strftime("%Y-%m")
                    monthly_pl[month] += realized_pl
                    cp = closed_positions[isin]
                    cp["isin"] = isin
                    cp["name"] = name
                    cp["total_realized_pl"] += realized_pl
                    cp["closed_lots"] += 1
                    cp["total_shares_sold"] += shares
                else:
                    open_lots.append(lot)

            elif row["tx_type"] == "SELL":
                total_fees += fee
                total_trades += 1
                remaining = shares
                sell_proceeds = 0.0
                cost_basis_total = 0.0

                while remaining > 0.001 and open_lots:
                    lot = open_lots[0]
                    used = min(remaining, lot.shares)
                    ratio = used / lot.shares
                    sell_proceeds += used * price
                    cost_basis_total += lot.total_cost * ratio
                    lot.total_cost -= lot.total_cost * ratio
                    lot.shares -= used
                    remaining -= used
                    if lot.shares < 0.001:
                        open_lots.pop(0)

                if remaining > 0.001:
                    logger.warning(
                        "SELL %s exceeds bought quantity: %.4f shares unmatched",
                        isin, remaining,
                    )
                    sell_proceeds += remaining * price
                    cost_basis_total += 0.0

                realized_pl = sell_proceeds - cost_basis_total - fee - tax
                month = row["datetime"].strftime("%Y-%m")
                monthly_pl[month] += realized_pl
                cp = closed_positions[isin]
                cp["isin"] = isin
                cp["name"] = name
                cp["total_realized_pl"] += realized_pl
                matched_shares = shares - remaining
                if matched_shares > 0.001:
                    cp["closed_lots"] += 1
                    cp["total_shares_sold"] += matched_shares

        tilg_mask = (cash_rows["tx_type"] == "TILG") & (cash_rows["symbol"] == isin)
        for _, tilg_row in cash_rows[tilg_mask].iterrows():
            if not _isna(tilg_row["amount"]):
                amount = abs(tilg_row["amount"])
                month = tilg_row["datetime"].strftime("%Y-%m")
                monthly_pl[month] += amount
                cp = closed_positions[isin]
                cp["total_realized_pl"] += amount

        if open_lots:
            remaining_shares = sum(l.shares for l in open_lots)
            total_cost_basis = sum(l.total_cost for l in open_lots)
            avg_cost = total_cost_basis / remaining_shares if remaining_shares > 0 else 0.0
            open_positions.append({
                "isin": isin,
                "name": name,
                "asset_class": rows[0]["asset_class"],
                "shares": round(remaining_shares, 6),
                "average_cost": round(avg_cost, 4),
                "total_cost": round(total_cost_basis, 2),
            })

        per_product[isin] = {
            "isin": isin,
            "name": name,
            "asset_class": rows[0]["asset_class"],
            "status": "open" if open_lots else "closed",
            "total_invested": round(total_invested, 2),
            "total_realized_pl": round(closed_positions[isin]["total_realized_pl"], 2),
            "total_dividends": 0.0,
            "total_fees": round(total_fees, 2),
            "total_trades": total_trades,
        }

    div_rows = cash_rows[cash_rows["tx_type"] == "DIVIDEND"]
    for _, row in div_rows.iterrows():
        isin = row["symbol"]
        if isin in per_product:
            per_product[isin]["total_dividends"] += abs(row["amount"])
    for isin in per_product:
        per_product[isin]["total_dividends"] = round(per_product[isin]["total_dividends"], 2)

    total_realized_pl = sum(cp["total_realized_pl"] for cp in closed_positions.values())

    summary = _compute_summary(df, cash_rows)
    summary["total_realized_pl"] = round(total_realized_pl, 2)
    summary["total_income"] = round(
        total_realized_pl
        + summary["total_dividends"]
        + summary["total_interest"]
        + summary["total_saveback"],
        2,
    )

    by_class = defaultdict(lambda: {"total_invested": 0.0, "total_realized_pl": 0.0, "total_dividends": 0.0, "total_fees": 0.0, "count": 0})
    for p in per_product.values():
        ac = p["asset_class"]
        by_class[ac]["total_invested"] += p["total_invested"]
        by_class[ac]["total_realized_pl"] += p["total_realized_pl"]
        by_class[ac]["total_dividends"] += p["total_dividends"]
        by_class[ac]["total_fees"] += p["total_fees"]
        by_class[ac]["count"] += 1
    summary["by_asset_class"] = {k: {sk: round(sv, 2) for sk, sv in v.items()} for k, v in by_class.items()}

    cash_flow = _compute_cash_flow(cash_rows)
    transactions = _get_recent_transactions(trades)

    return {
        "summary": summary,
        "open_positions": open_positions,
        "closed_positions": [v for v in closed_positions.values() if v["closed_lots"] > 0],
        "cash_flow": cash_flow,
        "transactions": transactions,
        "products": list(per_product.values()),
        "monthly_pl": [{"month": m, "realized_pl": round(v, 2)} for m, v in sorted(monthly_pl.items())],
    }


def compute_derivative_executions(df, knocked_ids):
    deriv = df[df["asset_class"] == "DERIVATIVE"].copy()
    if deriv.empty:
        return []

    buys = deriv[deriv["tx_type"] == "BUY"]
    warrant_ex = deriv[deriv["type"] == "WARRANT_EXERCISE"]
    tilg = deriv[deriv["tx_type"] == "TILG"]

    by_isin = {}

    for _, row in buys.iterrows():
        isin = row["symbol"]
        if isin not in by_isin:
            by_isin[isin] = {"name": row["name"], "isin": isin, "asset_class": "DERIVATIVE",
                             "ko_quantity": 0.0, "ko_loss": 0.0, "ko_fees": 0.0,
                             "warrant_quantity": 0.0, "warrant_return": 0.0}
        if row.get("transaction_id") in knocked_ids:
            entry = by_isin[isin]
            entry["ko_quantity"] += row["shares"]
            price = abs(row["price"]) if not _isna(row["price"]) else 0.0
            fee = abs(row["fee"]) if not _isna(row["fee"]) else 0.0
            entry["ko_loss"] += -(row["shares"] * price)
            entry["ko_fees"] += -fee

    for _, row in warrant_ex.iterrows():
        isin = row["symbol"]
        if isin not in by_isin:
            by_isin[isin] = {"name": row["name"], "isin": isin, "asset_class": "DERIVATIVE",
                             "ko_quantity": 0.0, "ko_loss": 0.0, "ko_fees": 0.0,
                             "warrant_quantity": 0.0, "warrant_return": 0.0}
        by_isin[isin]["warrant_quantity"] += abs(row["shares"])

    for _, row in tilg.iterrows():
        isin = row["symbol"]
        if isin not in by_isin:
            by_isin[isin] = {"name": row["name"], "isin": isin, "asset_class": "DERIVATIVE",
                             "ko_quantity": 0.0, "ko_loss": 0.0, "ko_fees": 0.0,
                             "warrant_quantity": 0.0, "warrant_return": 0.0}
        if not _isna(row["amount"]):
            by_isin[isin]["warrant_return"] += abs(row["amount"])

    result = []
    for entry in by_isin.values():
        if entry["ko_quantity"] == 0 and entry["warrant_quantity"] == 0 and entry["warrant_return"] == 0:
            continue
        entry["ko_loss"] = round(entry["ko_loss"], 2)
        entry["ko_fees"] = round(entry["ko_fees"], 2)
        entry["ko_total"] = round(entry["ko_loss"] + entry["ko_fees"], 2)
        entry["warrant_return"] = round(entry["warrant_return"], 2)
        entry["net_result"] = round(entry["ko_total"] + entry["warrant_return"], 2)
        entry["reconciled"] = abs(entry["ko_quantity"] - entry["warrant_quantity"]) < 0.01
        result.append(entry)

    return sorted(result, key=lambda x: x["name"])


def auto_detect_knocked(df):
    deriv = df[df["asset_class"] == "DERIVATIVE"].copy()
    if deriv.empty:
        return set()

    buys = deriv[deriv["tx_type"] == "BUY"].copy()
    regular_sells = deriv[(deriv["tx_type"] == "SELL") & (deriv["type"] != "WARRANT_EXERCISE")].copy()
    warrant_ex = deriv[deriv["type"] == "WARRANT_EXERCISE"].copy()

    auto_ids = set()

    for isin in deriv["symbol"].unique():
        isin_buys = buys[buys["symbol"] == isin]
        isin_we = warrant_ex[warrant_ex["symbol"] == isin]
        if isin_we.empty:
            continue

        total_we = isin_we["shares"].sum()

        lots = [[row["shares"], row["transaction_id"]] for _, row in isin_buys.iterrows()]

        for _, sell_row in regular_sells[regular_sells["symbol"] == isin].iterrows():
            remaining = sell_row["shares"]
            while remaining > 0.001 and lots:
                lot = lots[0]
                used = min(remaining, lot[0])
                lot[0] -= used
                remaining -= used
                if lot[0] < 0.001:
                    lots.pop(0)

        remaining_shares = sum(lot[0] for lot in lots)

        if abs(remaining_shares - total_we) < 0.01:
            for lot in lots:
                auto_ids.add(lot[1])

    return auto_ids


def compute_card_transactions(df):
    card = df[df["tx_type"] == "CARD"].sort_values("datetime", ascending=False).copy()
    result = []
    for _, row in card.iterrows():
        result.append({
            "id": row.get("transaction_id", ""),
            "datetime": row["datetime"].isoformat(),
            "name": row["name"],
            "amount": round(abs(row["amount"]), 2) if not _isna(row["amount"]) else None,
            "description": row.get("description", ""),
        })
    return result


def _isna(val):
    return val is None or (isinstance(val, float) and math.isnan(val))


def _compute_summary(df, cash_rows):
    deposits = cash_rows[cash_rows["tx_type"] == "DEPOSIT"]["amount"].sum()
    withdrawals = abs(cash_rows[cash_rows["tx_type"] == "WITHDRAWAL"]["amount"].sum())
    dividends = cash_rows[cash_rows["tx_type"] == "DIVIDEND"]["amount"].sum()
    interest = cash_rows[cash_rows["tx_type"] == "INTEREST"]["amount"].sum()
    saveback = cash_rows[cash_rows["tx_type"] == "SAVEBACK"]["amount"].sum()
    fees = abs(cash_rows[cash_rows["tx_type"] == "FEE"]["amount"].sum()) + abs(df["fee"].dropna().sum())
    card_spending = abs(cash_rows[cash_rows["tx_type"] == "CARD"]["amount"].sum())

    total_buys = abs(df[df["tx_type"] == "BUY"]["amount"].sum())
    total_sells = df[df["tx_type"] == "SELL"]["amount"].sum()
    invested = total_buys - total_sells

    return {
        "total_deposits": round(deposits, 2),
        "total_withdrawals": round(withdrawals, 2),
        "net_deposits": round(deposits - withdrawals, 2),
        "total_dividends": round(dividends, 2),
        "total_interest": round(interest, 2),
        "total_saveback": round(saveback, 2),
        "total_fees": round(fees, 2),
        "total_card_spending": round(card_spending, 2),
        "total_invested": round(invested, 2),
    }


def _compute_cash_flow(cash_rows):
    monthly = cash_rows.copy()
    monthly["month"] = monthly["datetime"].dt.to_period("M").astype(str)
    flow_types = ["DEPOSIT", "WITHDRAWAL", "DIVIDEND", "INTEREST"]
    result = []
    for month, group in monthly.groupby("month"):
        entry = {"month": month}
        for t in flow_types:
            val = group[group["tx_type"] == t]["amount"].sum()
            entry[t.lower()] = round(abs(val) if t == "WITHDRAWAL" else val, 2)
        result.append(entry)
    return sorted(result, key=lambda x: x["month"])


def _get_recent_transactions(trades, limit=50):
    recent = trades.tail(limit).iloc[::-1]
    result = []
    for _, row in recent.iterrows():
        result.append({
            "id": row.get("transaction_id", ""),
            "datetime": row["datetime"].isoformat(),
            "type": row["tx_type"],
            "name": row["name"],
            "symbol": row["symbol"],
            "shares": round(row["shares"], 6),
            "price": round(row["price"], 4) if not _isna(row["price"]) else None,
            "amount": round(row["amount"], 2) if not _isna(row["amount"]) else None,
            "asset_class": row["asset_class"],
        })
    return result

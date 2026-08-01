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
    datetime: object = None


def _empty_product(isin, name, asset_class):
    return {
        "isin": isin,
        "name": name,
        "asset_class": asset_class,
        "status": "closed",
        "total_invested": 0.0,
        "total_realized_pl": 0.0,
        "total_dividends": 0.0,
        "total_dividend_tax": 0.0,
        "total_dividends_net": 0.0,
        "total_fees": 0.0,
        "total_trades": 0,
    }


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
    lot_matches = []
    per_product = {}

    open_positions = []
    closed_positions = defaultdict(lambda: {
        "isin": "", "name": "", "total_realized_pl": 0.0,
        "closed_lots": 0, "total_shares_sold": 0.0,
    })

    tilg_by_isin = defaultdict(list)
    for _, r in cash_rows[cash_rows["tx_type"] == "TILG"].iterrows():
        tilg_by_isin[r["symbol"]].append(r)

    all_isins = list(by_isin.keys()) + [i for i in tilg_by_isin if i not in by_isin]

    for isin in all_isins:
        rows = by_isin.get(isin, [])
        tilg_rows = tilg_by_isin.get(isin, [])
        if rows:
            name = rows[0]["name"]
            asset_class = rows[0]["asset_class"]
        else:
            name = tilg_rows[0]["name"] or isin
            asset_class = tilg_rows[0]["asset_class"]
        total_invested = 0.0
        total_fees = 0.0
        total_trades = 0
        lot_id_gen = iter(range(1, 10**9))
        open_lots = []

        last_dt = None

        events = [(row["datetime"], 0, row) for row in rows]
        events += [(r["datetime"], 1, r) for r in tilg_rows]
        events.sort(key=lambda e: (e[0], e[1]))

        for _, kind, row in events:
            last_dt = row["datetime"]
            if kind == 1:
                amount = 0.0 if _isna(row["amount"]) else abs(row["amount"])
                cost = sum(l.total_cost for l in open_lots)
                shares_taken = sum(l.shares for l in open_lots)
                realized_pl = amount - cost
                month = row["datetime"].strftime("%Y-%m")
                monthly_pl[month] += realized_pl
                cp = closed_positions[isin]
                cp["isin"] = isin
                cp["name"] = name
                cp["total_realized_pl"] += realized_pl
                if shares_taken > 0.001:
                    cp["closed_lots"] += 1
                    cp["total_shares_sold"] += shares_taken
                for l in open_lots:
                    share_ratio = l.shares / shares_taken if shares_taken > 0 else 0.0
                    proceeds_lot = amount * share_ratio
                    lot_matches.append({
                        "isin": isin, "name": name,
                        "sell_id": str(row.get("transaction_id", "") or ""),
                        "sell_datetime": row["datetime"].isoformat(),
                        "lot_datetime": l.datetime.isoformat() if l.datetime else "",
                        "shares": round(l.shares, 6),
                        "proceeds": round(proceeds_lot, 2),
                        "cost_basis": round(l.total_cost, 2),
                        "pl": round(proceeds_lot - l.total_cost, 2),
                    })
                open_lots.clear()
                continue
            shares = row["shares"]
            price = abs(row["price"]) if not _isna(row["price"]) else 0.0
            fee = abs(row["fee"]) if not _isna(row["fee"]) else 0.0
            tax = abs(row["tax"]) if not _isna(row["tax"]) else 0.0
            total_cost = shares * price + fee + tax

            if row["tx_type"] == "BUY":
                total_invested += shares * price
                total_fees += fee
                total_trades += 1

                if row.get("knocked") is True:
                    lot = Lot(id=next(lot_id_gen), shares=shares, price=price, total_cost=total_cost,
                              datetime=row["datetime"])
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
                    lot_matches.append({
                        "isin": isin, "name": name, "sell_id": "",
                        "sell_datetime": ko_dt.isoformat(),
                        "lot_datetime": row["datetime"].isoformat(),
                        "shares": round(shares, 6),
                        "proceeds": 0.0,
                        "cost_basis": round(lot.total_cost, 2),
                        "pl": round(-lot.total_cost, 2),
                    })
                else:
                    to_allocate = shares
                    while to_allocate > 0.001 and open_lots and open_lots[0].shares < 0:
                        neg = open_lots[0]
                        covered = min(to_allocate, -neg.shares)
                        proceeds_portion = -neg.total_cost * (covered / -neg.shares)
                        cover_pl = proceeds_portion - covered * price
                        month = row["datetime"].strftime("%Y-%m")
                        monthly_pl[month] += cover_pl
                        cp = closed_positions[isin]
                        cp["isin"] = isin
                        cp["name"] = name
                        cp["total_realized_pl"] += cover_pl
                        cp["closed_lots"] += 1
                        cp["total_shares_sold"] += covered
                        lot_matches.append({
                            "isin": isin, "name": name,
                            "sell_id": str(row.get("transaction_id", "") or ""),
                            "sell_datetime": row["datetime"].isoformat(),
                            "lot_datetime": neg.datetime.isoformat() if neg.datetime else "",
                            "shares": round(covered, 6),
                            "proceeds": round(proceeds_portion, 2),
                            "cost_basis": round(covered * price, 2),
                            "pl": round(cover_pl, 2),
                        })
                        neg.shares += covered
                        neg.total_cost += proceeds_portion
                        to_allocate -= covered
                        if -neg.shares < 0.001:
                            monthly_pl[month] += -neg.total_cost
                            cp["total_realized_pl"] += -neg.total_cost
                            open_lots.pop(0)
                    if to_allocate > 0:
                        ratio = to_allocate / shares
                        lot_cost = to_allocate * price + (fee + tax) * ratio
                        open_lots.append(Lot(id=next(lot_id_gen), shares=to_allocate,
                                             price=price, total_cost=lot_cost,
                                             datetime=row["datetime"]))

            elif row["tx_type"] == "SELL":
                total_fees += fee
                total_trades += 1
                remaining = shares
                sell_proceeds = 0.0
                cost_basis_total = 0.0

                while remaining > 0.001 and open_lots and open_lots[0].shares > 0:
                    lot = open_lots[0]
                    used = min(remaining, lot.shares)
                    ratio = used / lot.shares
                    lot_cost_portion = lot.total_cost * ratio
                    sell_proceeds += used * price
                    cost_basis_total += lot_cost_portion
                    lot_matches.append({
                        "isin": isin, "name": name,
                        "sell_id": str(row.get("transaction_id", "") or ""),
                        "sell_datetime": row["datetime"].isoformat(),
                        "lot_datetime": lot.datetime.isoformat() if lot.datetime else "",
                        "shares": round(used, 6),
                        "proceeds": round(used * price, 2),
                        "cost_basis": round(lot_cost_portion, 2),
                        "pl": round(used * price - lot_cost_portion, 2),
                    })
                    lot.total_cost -= lot_cost_portion
                    lot.shares -= used
                    remaining -= used
                    if lot.shares < 0.001:
                        cost_basis_total += lot.total_cost
                        open_lots.pop(0)

                if 0 < remaining <= 0.001:
                    sell_proceeds += remaining * price
                    remaining = 0.0

                if remaining > 0.001:
                    if price > 0:
                        logger.warning(
                            "SELL %s exceeds bought quantity: %.4f shares tracked as short",
                            isin, remaining,
                        )
                        open_lots.append(Lot(id=next(lot_id_gen), shares=-remaining,
                                             price=price, total_cost=-(remaining * price),
                                             datetime=row["datetime"]))
                    else:
                        logger.info(
                            "SELL %s: %.4f unmatched shares at zero price (expiration), ignored",
                            isin, remaining,
                        )

                realized_pl = sell_proceeds - cost_basis_total - fee - tax
                month = row["datetime"].strftime("%Y-%m")
                if realized_pl != 0:
                    monthly_pl[month] += realized_pl
                cp = closed_positions[isin]
                cp["isin"] = isin
                cp["name"] = name
                cp["total_realized_pl"] += realized_pl
                matched_shares = shares - remaining
                if matched_shares > 0.001:
                    cp["closed_lots"] += 1
                    cp["total_shares_sold"] += matched_shares

        dust_cost = sum(l.total_cost for l in open_lots if abs(l.shares) < 0.001)
        open_lots = [l for l in open_lots if abs(l.shares) >= 0.001]
        if abs(dust_cost) > 0 and last_dt is not None:
            month = last_dt.strftime("%Y-%m")
            monthly_pl[month] += -dust_cost
            cp = closed_positions[isin]
            cp["isin"] = isin
            cp["name"] = name
            cp["total_realized_pl"] += -dust_cost

        if open_lots:
            remaining_shares = sum(l.shares for l in open_lots)
            total_cost_basis = sum(l.total_cost for l in open_lots)
            avg_cost = total_cost_basis / remaining_shares if abs(remaining_shares) > 0 else 0.0
            open_positions.append({
                "isin": isin,
                "name": name,
                "asset_class": asset_class,
                "shares": round(remaining_shares, 6),
                "average_cost": round(avg_cost, 4),
                "total_cost": round(total_cost_basis, 2),
            })

        per_product[isin] = {
            "isin": isin,
            "name": name,
            "asset_class": asset_class,
            "status": "open" if open_lots else "closed",
            "total_invested": round(total_invested, 2),
            "total_realized_pl": round(closed_positions[isin]["total_realized_pl"], 2),
            "total_dividends": 0.0,
            "total_dividend_tax": 0.0,
            "total_dividends_net": 0.0,
            "total_fees": round(total_fees, 2),
            "total_trades": total_trades,
        }

    div_rows = cash_rows[cash_rows["tx_type"] == "DIVIDEND"]
    for _, row in div_rows.iterrows():
        isin = row["symbol"]
        if not isin:
            continue
        if isin not in per_product:
            per_product[isin] = _empty_product(isin, row["name"], row["asset_class"])
        gross = row["amount"] if not _isna(row["amount"]) else 0.0
        wht = abs(row["tax"]) if not _isna(row["tax"]) else 0.0
        per_product[isin]["total_dividends"] += gross
        per_product[isin]["total_dividend_tax"] += wht
        per_product[isin]["total_dividends_net"] += gross - wht
    for isin in per_product:
        per_product[isin]["total_dividends"] = round(per_product[isin]["total_dividends"], 2)
        per_product[isin]["total_dividend_tax"] = round(per_product[isin]["total_dividend_tax"], 2)
        per_product[isin]["total_dividends_net"] = round(per_product[isin]["total_dividends_net"], 2)

    open_cost_by_isin = {p["isin"]: p["total_cost"] for p in open_positions}
    for isin, p in per_product.items():
        cost = open_cost_by_isin.get(isin)
        if cost and cost > 0:
            p["yield_on_cost"] = round(100 * p["total_dividends_net"] / cost, 2)
        else:
            p["yield_on_cost"] = None

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

    cash_balance = df["amount"].sum() - summary["total_dividend_tax"]
    trade_rows = df[df["tx_type"].isin(["BUY", "SELL"])]
    trade_fees = abs(trade_rows["fee"].dropna().sum()) if "fee" in trade_rows.columns else 0.0
    trade_taxes = abs(trade_rows["tax"].dropna().sum()) if "tax" in trade_rows.columns else 0.0
    fee_rows = cash_rows[cash_rows["tx_type"] == "FEE"]
    standalone_fee_col = abs(fee_rows["fee"].dropna().sum()) if "fee" in fee_rows.columns else 0.0
    cash_balance -= trade_fees + trade_taxes + standalone_fee_col
    open_cost = sum(p["total_cost"] for p in open_positions)
    standalone_fees = abs(fee_rows["amount"].sum()) + standalone_fee_col
    income = summary["total_dividends_net"] + summary["total_interest"] + summary["total_saveback"]
    sources = summary["net_deposits"] + income + summary["total_realized_pl"]
    uses = cash_balance + open_cost + summary["total_card_spending"] + standalone_fees
    summary["reconciliation"] = {
        "net_deposits": summary["net_deposits"],
        "income": round(income, 2),
        "realized_pl": summary["total_realized_pl"],
        "cash_balance": round(cash_balance, 2),
        "open_positions_cost": round(open_cost, 2),
        "card_spending": summary["total_card_spending"],
        "fees": round(standalone_fees, 2),
        "difference": round(sources - uses, 2),
    }

    by_class = defaultdict(lambda: {"total_invested": 0.0, "total_realized_pl": 0.0, "total_dividends": 0.0,
                                    "total_dividend_tax": 0.0, "total_fees": 0.0, "count": 0})
    for p in per_product.values():
        ac = p["asset_class"]
        by_class[ac]["total_invested"] += p["total_invested"]
        by_class[ac]["total_realized_pl"] += p["total_realized_pl"]
        by_class[ac]["total_dividends"] += p["total_dividends"]
        by_class[ac]["total_dividend_tax"] += p["total_dividend_tax"]
        by_class[ac]["total_fees"] += p["total_fees"]
        by_class[ac]["count"] += 1
    summary["by_asset_class"] = {k: {sk: round(sv, 2) for sk, sv in v.items()} for k, v in by_class.items()}

    cash_flow = _compute_cash_flow(cash_rows)
    transactions = _get_recent_transactions(trades)

    return {
        "summary": summary,
        "open_positions": open_positions,
        "closed_positions": [
            v for v in closed_positions.values()
            if v["closed_lots"] > 0 or abs(v["total_realized_pl"]) > 0.005
        ],
        "cash_flow": cash_flow,
        "transactions": transactions,
        "products": list(per_product.values()),
        "monthly_pl": [{"month": m, "realized_pl": round(v, 2)} for m, v in sorted(monthly_pl.items())],
        "lot_matches": lot_matches,
    }


MCC_CATEGORIES = {
    "5411": "Groceries", "5499": "Groceries", "5412": "Groceries",
    "5812": "Restaurants", "5814": "Fast Food", "5813": "Bars",
    "5541": "Fuel", "5542": "Fuel",
    "4111": "Public Transport", "4121": "Taxi & Rideshare", "4789": "Transport",
    "5311": "Department Stores", "5651": "Clothing", "5732": "Electronics",
    "5912": "Pharmacy", "5977": "Cosmetics",
    "4814": "Telecom", "4899": "Streaming & TV",
    "5734": "Software", "7372": "Software", "5817": "Digital Goods", "5818": "Digital Goods",
    "6011": "ATM Withdrawal", "4900": "Utilities",
    "7832": "Cinema", "7941": "Sports", "7922": "Events",
    "5944": "Jewelry", "5999": "Misc Shopping", "5947": "Gifts",
    "7011": "Hotels", "3000": "Travel", "4511": "Travel",
}


def compute_spending(df):
    card = df[df["tx_type"] == "CARD"]
    by_category = defaultdict(float)
    by_month = defaultdict(float)
    for _, row in card.iterrows():
        amount = row["amount"] if not _isna(row["amount"]) else 0.0
        mcc = str(row.get("mcc_code", "") or "").strip()
        category = MCC_CATEGORIES.get(mcc, "Other")
        by_category[category] += -amount
        by_month[row["datetime"].strftime("%Y-%m")] += -amount
    categories = [
        {"category": c, "total": round(t, 2)}
        for c, t in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
        if abs(t) > 0.005
    ]
    monthly = [
        {"month": m, "total": round(t, 2)}
        for m, t in sorted(by_month.items())
    ]
    return {"by_category": categories, "monthly": monthly}


def compute_income(df):
    monthly = defaultdict(lambda: {"dividends": 0.0, "interest": 0.0, "saveback": 0.0})
    dividends = []
    for _, row in df.iterrows():
        month = row["datetime"].strftime("%Y-%m")
        amount = row["amount"] if not _isna(row["amount"]) else 0.0
        if row["tx_type"] == "DIVIDEND":
            wht = abs(row["tax"]) if not _isna(row["tax"]) else 0.0
            monthly[month]["dividends"] += amount - wht
            currency = row.get("original_currency") or row.get("currency") or ""
            dividends.append({
                "date": row["datetime"].isoformat()[:10],
                "name": row["name"],
                "isin": row["symbol"],
                "gross": round(amount, 2),
                "wht": round(wht, 2),
                "net": round(amount - wht, 2),
                "currency": currency,
            })
        elif row["tx_type"] == "INTEREST":
            monthly[month]["interest"] += amount
        elif row["tx_type"] == "SAVEBACK":
            monthly[month]["saveback"] += amount
    monthly_list = [
        {
            "month": m,
            "dividends": round(v["dividends"], 2),
            "interest": round(v["interest"], 2),
            "saveback": round(v["saveback"], 2),
            "total": round(v["dividends"] + v["interest"] + v["saveback"], 2),
        }
        for m, v in sorted(monthly.items())
    ]
    dividends.sort(key=lambda x: x["date"], reverse=True)
    return {"monthly": monthly_list, "dividends": dividends}


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
                             "ko_quantity": 0.0, "ko_loss": 0.0, "ko_fees": 0.0, "ko_tax": 0.0,
                             "warrant_quantity": 0.0, "warrant_return": 0.0}
        if row.get("transaction_id") in knocked_ids:
            entry = by_isin[isin]
            entry["ko_quantity"] += row["shares"]
            price = abs(row["price"]) if not _isna(row["price"]) else 0.0
            fee = abs(row["fee"]) if not _isna(row["fee"]) else 0.0
            entry["ko_loss"] += -(row["shares"] * price)
            entry["ko_fees"] += -fee
            tax = abs(row["tax"]) if not _isna(row["tax"]) else 0.0
            entry["ko_tax"] += -tax

    for _, row in warrant_ex.iterrows():
        isin = row["symbol"]
        if isin not in by_isin:
            by_isin[isin] = {"name": row["name"], "isin": isin, "asset_class": "DERIVATIVE",
                             "ko_quantity": 0.0, "ko_loss": 0.0, "ko_fees": 0.0, "ko_tax": 0.0,
                             "warrant_quantity": 0.0, "warrant_return": 0.0}
        by_isin[isin]["warrant_quantity"] += abs(row["shares"])

    for _, row in tilg.iterrows():
        isin = row["symbol"]
        if isin not in by_isin:
            by_isin[isin] = {"name": row["name"], "isin": isin, "asset_class": "DERIVATIVE",
                             "ko_quantity": 0.0, "ko_loss": 0.0, "ko_fees": 0.0, "ko_tax": 0.0,
                             "warrant_quantity": 0.0, "warrant_return": 0.0}
        if not _isna(row["amount"]):
            by_isin[isin]["warrant_return"] += abs(row["amount"])

    result = []
    for entry in by_isin.values():
        if entry["ko_quantity"] == 0 and entry["warrant_quantity"] == 0 and entry["warrant_return"] == 0:
            continue
        entry["ko_loss"] = round(entry["ko_loss"], 2)
        entry["ko_fees"] = round(entry["ko_fees"], 2)
        entry["ko_tax"] = round(entry["ko_tax"], 2)
        entry["ko_total"] = round(entry["ko_loss"] + entry["ko_fees"] + entry["ko_tax"], 2)
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
    dividend_tax = abs(cash_rows[cash_rows["tx_type"] == "DIVIDEND"]["tax"].dropna().sum())
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
        "total_dividend_tax": round(dividend_tax, 2),
        "total_dividends_net": round(dividends - dividend_tax, 2),
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


def apply_prices(open_positions, prices):
    positions = []
    total_value = 0.0
    total_unrealized = 0.0
    for p in open_positions:
        price = prices.get(p["isin"])
        row = dict(p)
        if price is not None:
            row["market_price"] = price
            row["market_value"] = round(p["shares"] * price, 2)
            row["unrealized_pl"] = round(p["shares"] * price - p["total_cost"], 2)
            total_value += row["market_value"]
            total_unrealized += row["unrealized_pl"]
        else:
            row["market_price"] = None
            row["market_value"] = None
            row["unrealized_pl"] = None
        positions.append(row)
    return {
        "positions": positions,
        "totals": {
            "market_value": round(total_value, 2),
            "unrealized_pl": round(total_unrealized, 2),
        },
    }

def xirr(flows):
    """Money-weighted annualized return via bisection. flows: [(datetime, amount)].

    Negative amounts are money invested, positive amounts are money returned.
    Returns None when no sign change brackets a solution.
    """
    if not flows:
        return None
    amounts = [a for _, a in flows]
    if not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)):
        return None
    t0 = min(d for d, _ in flows)

    def npv(rate):
        return sum(a / (1 + rate) ** ((d - t0).days / 365.0) for d, a in flows)

    lo, hi = -0.9999, 10.0
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if abs(fm) < 1e-9:
            return mid
        if flo * fm < 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def compute_performance(df, result):
    summary = result["summary"]
    open_cost = sum(p["total_cost"] for p in result["open_positions"])
    cash_balance = summary.get("reconciliation", {}).get("cash_balance", 0.0)
    terminal_value = round(cash_balance + open_cost, 2)

    flows = []
    for _, row in df[df["tx_type"].isin({"DEPOSIT", "WITHDRAWAL"})].iterrows():
        amount = row["amount"]
        flows.append((row["datetime"], -amount))
    if not df.empty:
        flows.append((df["datetime"].max(), terminal_value))
    rate = xirr(flows)

    closed = result["closed_positions"]
    wins = [c["total_realized_pl"] for c in closed if c["total_realized_pl"] > 0]
    losses = [c["total_realized_pl"] for c in closed if c["total_realized_pl"] < 0]
    total_closed = len(wins) + len(losses)

    return {
        "xirr": round(rate, 4) if rate is not None else None,
        "terminal_value": terminal_value,
        "winners": len(wins),
        "losers": len(losses),
        "win_rate": round(100 * len(wins) / total_closed, 1) if total_closed else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
    }

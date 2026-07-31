# Accounting Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the accounting correctness issues found in the code review: disposal-date attribution for knock-outs, TILG cost-basis matching, unmatched sells, dividend withholding tax visibility, dust lots, derivative view consistency, and a reconciliation block.

**Architecture:** All calculation changes live in `portfolio/engine.py` and `portfolio/parser.py`. Frontend changes are limited to new columns/cards in `templates/index.html` and `static/dashboard.js`. No new dependencies.

**Tech Stack:** Python 3, pandas, Flask, pytest (run with `py -m pytest`), vanilla JS.

## Global Constraints

- Run tests with `py -m pytest tests -q` from the repo root (pytest is only installed for the `py` launcher, NOT in `.venv`). 34 tests currently pass.
- Do not use em dashes ("—") in any file or commit message. Use commas, colons, or parentheses.
- Commit style follows repo history: lowercase conventional prefix, e.g. `fix: ...`, `feat: ...`.
- Test DataFrames are built row-by-row with `pd.DataFrame([...])` and may lack the `type`, `transaction_id`, and `knocked` columns. All new engine code must tolerate missing columns (use `"type" in df.columns` guards and `row.get(...)`).
- `run_engine(df)` receives rows already classified by `portfolio/parser.py` (`tx_type` one of BUY, SELL, DEPOSIT, WITHDRAWAL, CARD, FEE, DIVIDEND, INTEREST, SAVEBACK, TILG, MIGRATION, OTHER).
- API key names in existing responses must not be renamed (the frontend depends on them). Only add new keys.

---

### Task 1: Parser hardening (dedup, MIGRATION type, file-like input)

**Files:**
- Modify: `portfolio/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `parse_csv(source)` where `source` is a path string OR a file-like object (e.g. `io.BytesIO`). Rows with `type == "MIGRATION"` get `tx_type == "MIGRATION"`. Rows with a duplicated non-empty `transaction_id` are dropped (first occurrence kept).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_parser.py`:

```python
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
        "2025-05-27T11:16:23.775580Z,2025-05-27,DEFAULT,CASH,TRANSFER_INSTANT_INBOUND,,,,,,1000.00,,EUR,,,,Incoming,id200,,,,",
        "2025-05-27T11:16:23.775580Z,2025-05-27,DEFAULT,CASH,TRANSFER_INSTANT_INBOUND,,,,,,1000.00,,EUR,,,,Incoming,id200,,,,",
        "2025-05-28T11:16:23.775580Z,2025-05-28,DEFAULT,CASH,TRANSFER_INSTANT_INBOUND,,,,,,500.00,,EUR,,,,Incoming,id201,,,,",
    ])
    df = parse_csv(str(csv))
    csv.unlink()
    assert len(df) == 2


def test_migration_rows_classified_and_balanced(caplog):
    csv = _make_csv([
        "2026-07-17T01:08:54.572Z,2026-07-17,DEFAULT,DELIVERY,MIGRATION,STOCK,Santander,ES0113900J37,-375.0,12.0487,,,EUR,,,,MIGRATION ES0113900J37,id300,,,,",
        "2026-07-17T01:08:54.581Z,2026-07-17,DEFAULT,DELIVERY,MIGRATION,STOCK,Santander,ES0113900J37,375.0,12.0487,,,EUR,,,,MIGRATION ES0113900J37,id301,,,,",
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
        "2026-07-17T01:08:54.572Z,2026-07-17,DEFAULT,DELIVERY,MIGRATION,STOCK,Santander,ES0113900J37,375.0,12.0487,,,EUR,,,,MIGRATION ES0113900J37,id302,,,,",
    ])
    import logging
    with caplog.at_level(logging.WARNING):
        df = parse_csv(str(csv))
    csv.unlink()
    assert df.iloc[0]["tx_type"] == "MIGRATION"
    assert any("Unpaired MIGRATION" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_parser.py -q`
Expected: FAIL (4 new tests fail: BytesIO works already but dedup/MIGRATION do not; at minimum `test_duplicate_transaction_id_dropped`, `test_migration_rows_classified_and_balanced`, and `test_unpaired_migration_warns` fail).

- [ ] **Step 3: Implement parser changes**

Replace the whole of `portfolio/parser.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 38 passed.

- [ ] **Step 5: Commit**

```bash
git add portfolio/parser.py tests/test_parser.py
git commit -m "fix: dedup by transaction_id, classify MIGRATION rows, accept file-like input in parser"
```

---

### Task 2: Knock-out loss booked at disposal (WARRANT_EXERCISE) date

**Files:**
- Modify: `portfolio/engine.py` (run_engine, lines 17-64 area)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: existing `run_engine(df)`.
- Produces: unchanged response shape. Only the `month` attribution of knocked-lot losses changes: the loss lands in the month of the earliest `WARRANT_EXERCISE` row for that ISIN, falling back to the buy month when no exercise row exists.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_engine.py -q`
Expected: 2 new tests FAIL (loss currently lands in the buy month: `2025-01` / `2025-12`).

- [ ] **Step 3: Implement disposal-date attribution**

In `portfolio/engine.py`, inside `run_engine`, right after the `cash_rows = ...` line (line 19), add:

```python
    we_dates = {}
    if "type" in df.columns:
        for _, r in df[df["type"] == "WARRANT_EXERCISE"].iterrows():
            d = r["datetime"]
            if r["symbol"] not in we_dates or d < we_dates[r["symbol"]]:
                we_dates[r["symbol"]] = d
```

Then change the knocked branch (currently lines 55-58) from:

```python
                if row.get("knocked") is True:
                    realized_pl = -lot.total_cost
                    month = row["datetime"].strftime("%Y-%m")
```

to:

```python
                if row.get("knocked") is True:
                    realized_pl = -lot.total_cost
                    ko_dt = we_dates.get(isin, row["datetime"])
                    month = ko_dt.strftime("%Y-%m")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 40 passed (existing knocked tests without a WARRANT_EXERCISE row keep the buy-month fallback).

- [ ] **Step 5: Commit**

```bash
git add portfolio/engine.py tests/test_engine.py
git commit -m "fix: attribute knock-out losses to the exercise month, not the buy month"
```

---

### Task 3: TILG as FIFO disposal (position termination)

**Files:**
- Modify: `portfolio/engine.py` (run_engine per-ISIN loop, lines 34-147 area)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `we_dates` behavior from Task 2 (unchanged).
- Produces: unchanged response shape. Behavior changes: a TILG row now terminates the open lots of that ISIN at the TILG date (realized = TILG amount − remaining cost basis) instead of being booked as pure profit. TILG rows for ISINs with no trades are now included. Closed positions filter becomes `closed_lots > 0 or abs(total_realized_pl) > 0.005`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_engine.py -q`
Expected: 3 new tests FAIL (TILG currently booked as +300 pure profit with lots still open; TILG-only ISIN dropped entirely).

- [ ] **Step 3: Implement TILG disposal**

In `portfolio/engine.py`, before the `for isin, rows in by_isin.items():` loop, add:

```python
    tilg_by_isin = defaultdict(list)
    for _, r in cash_rows[cash_rows["tx_type"] == "TILG"].iterrows():
        tilg_by_isin[r["symbol"]].append(r)

    all_isins = list(by_isin.keys()) + [i for i in tilg_by_isin if i not in by_isin]
```

Change the loop header and the `name`/loop-setup lines from:

```python
    for isin, rows in by_isin.items():
        name = rows[0]["name"]
```

to:

```python
    for isin in all_isins:
        rows = by_isin.get(isin, [])
        tilg_rows = tilg_by_isin.get(isin, [])
        if rows:
            name = rows[0]["name"]
            asset_class = rows[0]["asset_class"]
        else:
            name = tilg_rows[0]["name"] or isin
            asset_class = tilg_rows[0]["asset_class"]
```

Build the merged, chronological event list right after the `open_lots = []` line:

```python
        events = [(row["datetime"], 0, row) for row in rows]
        events += [(r["datetime"], 1, r) for r in tilg_rows]
        events.sort(key=lambda e: (e[0], e[1]))
```

Replace the trade loop header `for row in rows:` with:

```python
        for _, kind, row in events:
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
                open_lots.clear()
                continue
```

(The rest of the loop body, the BUY/SELL handling, stays unchanged.)

Delete the old TILG block after the trade loop:

```python
        tilg_mask = (cash_rows["tx_type"] == "TILG") & (cash_rows["symbol"] == isin)
        for _, tilg_row in cash_rows[tilg_mask].iterrows():
            if not _isna(tilg_row["amount"]):
                amount = abs(tilg_row["amount"])
                month = tilg_row["datetime"].strftime("%Y-%m")
                monthly_pl[month] += amount
                cp = closed_positions[isin]
                cp["total_realized_pl"] += amount
```

In the `open_positions.append({...})` and `per_product[isin] = {...}` blocks, replace `rows[0]["asset_class"]` with the new `asset_class` variable (two occurrences), so TILG-only ISINs work.

Change the closed positions filter in the return dict from:

```python
        "closed_positions": [v for v in closed_positions.values() if v["closed_lots"] > 0],
```

to:

```python
        "closed_positions": [
            v for v in closed_positions.values()
            if v["closed_lots"] > 0 or abs(v["total_realized_pl"]) > 0.005
        ],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 43 passed.

- [ ] **Step 5: Commit**

```bash
git add portfolio/engine.py tests/test_engine.py
git commit -m "fix: treat TILG as FIFO disposal of remaining lots at the TILG date"
```

---

### Task 4: Unmatched sells tracked as short positions (covered by later buys)

**Files:**
- Modify: `portfolio/engine.py` (SELL and BUY branches in run_engine)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: the merged event loop from Task 3.
- Produces: unmatched SELL quantity with `price > 0` creates a negative open lot (negative `shares`, negative `total_cost` in `open_positions`) instead of immediate zero-cost profit. A later BUY covers the short FIFO and books `proceeds − cover cost` as realized P&L at the buy date. Unmatched zero-price sells (expirations) are ignored with an info log.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_engine.py -q`
Expected: 3 new tests FAIL (current code books +600 instant profit and, after Task 3, would also create negative lots for zero-price expirations if unguarded).

- [ ] **Step 3: Implement short tracking**

In `portfolio/engine.py`, replace the BUY branch:

```python
            if row["tx_type"] == "BUY":
                total_invested += shares * price
                total_fees += fee
                total_trades += 1
                lot = Lot(id=next(lot_id_gen), shares=shares, price=price, total_cost=total_cost)

                if row.get("knocked") is True:
```

... (keep the knocked sub-branch unchanged) ...

```python
                else:
                    open_lots.append(lot)
```

with:

```python
            if row["tx_type"] == "BUY":
                total_invested += shares * price
                total_fees += fee
                total_trades += 1

                if row.get("knocked") is True:
                    lot = Lot(id=next(lot_id_gen), shares=shares, price=price, total_cost=total_cost)
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
                        neg.shares += covered
                        neg.total_cost += proceeds_portion
                        to_allocate -= covered
                        if -neg.shares < 0.001:
                            monthly_pl[month] += -neg.total_cost
                            cp["total_realized_pl"] += -neg.total_cost
                            open_lots.pop(0)
                    if to_allocate > 0.001:
                        ratio = to_allocate / shares
                        lot_cost = to_allocate * price + (fee + tax) * ratio
                        open_lots.append(Lot(id=next(lot_id_gen), shares=to_allocate,
                                             price=price, total_cost=lot_cost))
```

(The knocked sub-branch content is identical to the old code, only the surrounding if/else structure changes so shorts are covered before lotting.)

In the SELL branch, change the matching while condition from:

```python
                while remaining > 0.001 and open_lots:
```

to:

```python
                while remaining > 0.001 and open_lots and open_lots[0].shares > 0:
```

and replace the unmatched block:

```python
                if remaining > 0.001:
                    logger.warning(
                        "SELL %s exceeds bought quantity: %.4f shares unmatched",
                        isin, remaining,
                    )
                    sell_proceeds += remaining * price
                    cost_basis_total += 0.0
```

with:

```python
                if remaining > 0.001:
                    if price > 0:
                        logger.warning(
                            "SELL %s exceeds bought quantity: %.4f shares tracked as short",
                            isin, remaining,
                        )
                        open_lots.append(Lot(id=next(lot_id_gen), shares=-remaining,
                                             price=price, total_cost=-(remaining * price)))
                    else:
                        logger.info(
                            "SELL %s: %.4f unmatched shares at zero price (expiration), ignored",
                            isin, remaining,
                        )
```

(Do NOT zero `remaining`: the existing `matched_shares = shares - remaining` line must keep seeing the unmatched quantity so only the matched part counts as sold. This is what keeps `test_warrant_exercise_no_duplicate_shares_sold` passing.)

Also guard the monthly P&L write in the SELL branch. Change:

```python
                realized_pl = sell_proceeds - cost_basis_total - fee - tax
                month = row["datetime"].strftime("%Y-%m")
                monthly_pl[month] += realized_pl
```

to:

```python
                realized_pl = sell_proceeds - cost_basis_total - fee - tax
                month = row["datetime"].strftime("%Y-%m")
                if realized_pl != 0:
                    monthly_pl[month] += realized_pl
```

(A fully unmatched short sell has realized_pl of exactly 0 at sale time; without the guard it would create a spurious zero month entry in the chart.)

In the open positions block, change the average-cost guard from:

```python
            avg_cost = total_cost_basis / remaining_shares if remaining_shares > 0 else 0.0
```

to:

```python
            avg_cost = total_cost_basis / remaining_shares if abs(remaining_shares) > 0 else 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 46 passed.

- [ ] **Step 5: Commit**

```bash
git add portfolio/engine.py tests/test_engine.py
git commit -m "fix: track unmatched sells as short lots covered by later buys"
```

---

### Task 5: Dust lots swept into realized P&L instead of vanishing

**Files:**
- Modify: `portfolio/engine.py` (SELL matching loop and open-positions block)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: SELL loop from Task 4.
- Produces: when a lot drops below 0.001 shares during matching, its leftover cost basis is added to that sale's cost (not silently dropped). Tiny unmatched sell remainders (<= 0.001 shares) add their proceeds to the sale. Dust lots still open at the end of an ISIN's history are written off as a loss in the last event month and excluded from `open_positions`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_engine.py -q`
Expected: 2 new tests FAIL (dust currently vanishes: realized 0.0, and the leftover dust lot shows as an open position).

- [ ] **Step 3: Implement dust sweeps**

In the SELL matching loop, change:

```python
                    lot.total_cost -= lot.total_cost * ratio
                    lot.shares -= used
                    remaining -= used
                    if lot.shares < 0.001:
                        open_lots.pop(0)
```

to:

```python
                    lot.total_cost -= lot.total_cost * ratio
                    lot.shares -= used
                    remaining -= used
                    if lot.shares < 0.001:
                        cost_basis_total += lot.total_cost
                        open_lots.pop(0)
```

Right after the while loop (before the unmatched handling from Task 4), add:

```python
                if 0 < remaining <= 0.001:
                    sell_proceeds += remaining * price
                    remaining = 0.0
```

Track the last event date: inside the event loop, add as the first line of the body (after `for _, kind, row in events:`):

```python
            last_dt = row["datetime"]
```

In the open positions block, replace:

```python
        if open_lots:
            remaining_shares = sum(l.shares for l in open_lots)
            total_cost_basis = sum(l.total_cost for l in open_lots)
```

with:

```python
        dust_cost = sum(l.total_cost for l in open_lots if abs(l.shares) < 0.001)
        open_lots = [l for l in open_lots if abs(l.shares) >= 0.001]
        if abs(dust_cost) > 0:
            month = last_dt.strftime("%Y-%m")
            monthly_pl[month] += -dust_cost
            cp = closed_positions[isin]
            cp["isin"] = isin
            cp["name"] = name
            cp["total_realized_pl"] += -dust_cost

        if open_lots:
            remaining_shares = sum(l.shares for l in open_lots)
            total_cost_basis = sum(l.total_cost for l in open_lots)
```

Note: `last_dt` must be initialized before the event loop as `last_dt = None` and the dust write-off guarded with `if abs(dust_cost) > 0 and last_dt is not None:`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 48 passed.

- [ ] **Step 5: Commit**

```bash
git add portfolio/engine.py tests/test_engine.py
git commit -m "fix: sweep fractional dust lots into realized P&L instead of dropping them"
```

---

### Task 6: Dividend withholding tax surfaced (gross, WHT, net)

**Files:**
- Modify: `portfolio/engine.py` (dividend loop, per_product dicts, `_compute_summary`, `by_asset_class` loop)
- Modify: `templates/index.html` (product table header)
- Modify: `static/dashboard.js` (TABLE_CONFIGS, formatVal, renderSummary)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: nothing from Tasks 2-5 (independent code region).
- Produces: new keys on products: `total_dividend_tax` (float), `total_dividends_net` (float). New keys on summary: `total_dividend_tax` (float), `total_dividends_net` (float). Dividend amounts are summed raw (no `abs()`), so negative adjustments reduce dividends. Dividends for ISINs with no trades now create a product row with `total_trades: 0` and `status: "closed"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_engine.py -q`
Expected: 3 new tests FAIL (no WHT keys; untraded ISIN dropped; `abs()` hides the negative adjustment).

- [ ] **Step 3: Implement WHT fields**

In `portfolio/engine.py`, add a helper above `run_engine`:

```python
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
```

In the per_product assignment for traded ISINs, add the two new keys with value `0.0` (`"total_dividend_tax": 0.0,` and `"total_dividends_net": 0.0,` right after `"total_dividends": 0.0,`).

Replace the dividend loop:

```python
    div_rows = cash_rows[cash_rows["tx_type"] == "DIVIDEND"]
    for _, row in div_rows.iterrows():
        isin = row["symbol"]
        if isin in per_product:
            per_product[isin]["total_dividends"] += abs(row["amount"])
    for isin in per_product:
        per_product[isin]["total_dividends"] = round(per_product[isin]["total_dividends"], 2)
```

with:

```python
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
```

In `_compute_summary`, after the `dividends = ...` line add:

```python
    dividend_tax = abs(cash_rows[cash_rows["tx_type"] == "DIVIDEND"]["tax"].dropna().sum())
```

and add to the returned dict, after `"total_dividends": round(dividends, 2),`:

```python
        "total_dividend_tax": round(dividend_tax, 2),
        "total_dividends_net": round(dividends - dividend_tax, 2),
```

In the `by_class` aggregation, change the defaultdict factory to:

```python
    by_class = defaultdict(lambda: {"total_invested": 0.0, "total_realized_pl": 0.0, "total_dividends": 0.0,
                                    "total_dividend_tax": 0.0, "total_fees": 0.0, "count": 0})
```

and add inside the loop, after `by_class[ac]["total_dividends"] += p["total_dividends"]`:

```python
        by_class[ac]["total_dividend_tax"] += p["total_dividend_tax"]
```

Frontend, in `templates/index.html` product table thead, after the Dividends `<th>` add:

```html
      <th data-sort="total_dividend_tax" class="num">Div. WHT</th>
```

In `static/dashboard.js`:
- In `TABLE_CONFIGS['product-results-table'].numericFields`, add `'total_dividend_tax'` after `'total_dividends'`.
- In `formatVal`, extend the EUR condition: add `|| key === 'total_dividend_tax' || key === 'total_dividends_net'`.
- In `renderSummary`, add a card after the Dividends card:

```javascript
{ label: "Dividend WHT", value: s.total_dividend_tax, fmt: v => `\u20AC${v.toLocaleString()}` },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 51 passed.

- [ ] **Step 5: Verify the dashboard manually**

Run: `.\run-dev.bat` (or `py app.py`), open http://localhost:5000, confirm the product table shows the Div. WHT column and the summary shows the Dividend WHT card (0,17 EUR for the Alphabet dividend in the real data).

- [ ] **Step 6: Commit**

```bash
git add portfolio/engine.py tests/test_engine.py templates/index.html static/dashboard.js
git commit -m "fix: surface dividend withholding tax (gross, WHT, net) in products and summary"
```

---

### Task 7: Derivative executions view includes buy tax (matches engine P&L)

**Files:**
- Modify: `portfolio/engine.py` (`compute_derivative_executions`)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: new key `ko_tax` (float, negative) on each derivative execution entry; `ko_total` becomes `ko_loss + ko_fees + ko_tax`, so `net_result` reconciles with `run_engine`'s `total_realized_pl` for the same instrument.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine.py` (add `compute_derivative_executions` to the import at the top: `from portfolio.engine import run_engine, auto_detect_knocked, compute_derivative_executions`):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_engine.py::test_derivative_executions_include_buy_tax -q`
Expected: FAIL (`ko_tax` KeyError, `ko_total` is -502.0).

- [ ] **Step 3: Implement ko_tax**

In `compute_derivative_executions`, in all three entry-template dicts, change:

```python
            by_isin[isin] = {"name": row["name"], "isin": isin, "asset_class": "DERIVATIVE",
                             "ko_quantity": 0.0, "ko_loss": 0.0, "ko_fees": 0.0,
                             "warrant_quantity": 0.0, "warrant_return": 0.0}
```

to (three occurrences, same edit):

```python
            by_isin[isin] = {"name": row["name"], "isin": isin, "asset_class": "DERIVATIVE",
                             "ko_quantity": 0.0, "ko_loss": 0.0, "ko_fees": 0.0, "ko_tax": 0.0,
                             "warrant_quantity": 0.0, "warrant_return": 0.0}
```

In the knocked-buy accumulation block, after `entry["ko_fees"] += -fee` add:

```python
            tax = abs(row["tax"]) if not _isna(row["tax"]) else 0.0
            entry["ko_tax"] += -tax
```

In the result loop, after `entry["ko_fees"] = round(entry["ko_fees"], 2)` add:

```python
        entry["ko_tax"] = round(entry["ko_tax"], 2)
```

and change `entry["ko_total"] = round(entry["ko_loss"] + entry["ko_fees"], 2)` to:

```python
        entry["ko_total"] = round(entry["ko_loss"] + entry["ko_fees"] + entry["ko_tax"], 2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 52 passed.

- [ ] **Step 5: Commit**

```bash
git add portfolio/engine.py tests/test_engine.py
git commit -m "fix: include buy tax in derivative execution KO totals"
```

---

### Task 8: Reconciliation block in summary

**Files:**
- Modify: `portfolio/engine.py` (end of run_engine)
- Modify: `templates/index.html` (new section)
- Modify: `static/dashboard.js` (render function)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `summary["total_dividends_net"]` and `summary["total_dividend_tax"]` from Task 6.
- Produces: `summary["reconciliation"]` dict with keys: `net_deposits`, `income`, `realized_pl`, `cash_balance`, `open_positions_cost`, `card_spending`, `fees`, `difference`. Identity: `net_deposits + income + realized_pl ≈ cash_balance + open_positions_cost + card_spending + fees + difference`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine.py`:

```python
def test_reconciliation_balances_on_full_cycle():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "DEPOSIT", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 2000.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-02", tz="UTC"), "tx_type": "BUY", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 50.0, "amount": -501.0, "fee": 1.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "X", "symbol": "X",
         "asset_class": "STOCK", "shares": 10.0, "price": 60.0, "amount": 599.0, "fee": 1.0, "tax": 0.0},
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_engine.py::test_reconciliation_balances_on_full_cycle -q`
Expected: FAIL (KeyError: 'reconciliation').

- [ ] **Step 3: Implement the reconciliation block**

In `run_engine`, after the `summary["total_income"] = ...` assignment, add:

```python
    cash_balance = df["amount"].sum() - summary["total_dividend_tax"]
    open_cost = sum(p["total_cost"] for p in open_positions)
    standalone_fees = abs(cash_rows[cash_rows["tx_type"] == "FEE"]["amount"].sum())
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
```

(`cash_balance` subtracts the dividend WHT because TR reports the gross amount while the tax was withheld at source and never touched the account.)

In `templates/index.html`, after the `summary-by-asset-class` section add:

```html
<section>
  <h2>Reconciliation</h2>
  <div class="table-wrapper">
  <table id="recon-table">
    <thead><tr><th>Line</th><th class="num">Amount</th></tr></thead>
    <tbody></tbody>
  </table>
  </div>
</section>
```

In `static/dashboard.js`, add a call `renderRecon(summary);` after `renderSummaryByAssetClass(summary);` in `loadAllData`, and add the function:

```javascript
function renderRecon(s) {
const tbody = document.querySelector("#recon-table tbody");
tbody.innerHTML = "";
if (!s.reconciliation) return;
const r = s.reconciliation;
const eur = v => `\u20AC${(v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const rows = [
  ["Net deposits", r.net_deposits],
  ["Income (dividends net, interest, saveback)", r.income],
  ["Realized P&L", r.realized_pl],
  ["Cash balance", r.cash_balance],
  ["Open positions at cost", r.open_positions_cost],
  ["Card spending", r.card_spending],
  ["Standalone fees", r.fees],
  ["Unreconciled difference", r.difference],
];
rows.forEach(([label, val], i) => {
  const tr = document.createElement("tr");
  if (i === rows.length - 1) tr.className = "total-row";
  tr.innerHTML = `<td>${label}</td><td class="num">${eur(val)}</td>`;
  tbody.appendChild(tr);
});
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 53 passed.

- [ ] **Step 5: Verify against the real data**

Run the app, open http://localhost:5000, and check the Reconciliation section: the difference should be small (a few euros at most, from FX conversions and TR amount rounding). If it is large, investigate before proceeding.

- [ ] **Step 6: Commit**

```bash
git add portfolio/engine.py tests/test_engine.py templates/index.html static/dashboard.js
git commit -m "feat: add reconciliation block (sources vs uses) to summary"
```

---

### Task 9: Cache engine results per API call cycle; upload without temp file

**Files:**
- Modify: `app.py`
- Test: `tests/test_app.py` (new file)

**Interfaces:**
- Consumes: `parse_csv` accepting file-like objects (Task 1).
- Produces: `app.invalidate_cache()` (no args, no return). `compute_data(flagged_ids)` returns a cached result when called repeatedly with the same ids and unchanged dataframe. Upload no longer writes a temp file.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_app.py -q`
Expected: FAIL (`invalidate_cache` does not exist; second test may pass already or fail depending on temp-file behavior, the first must fail).

- [ ] **Step 3: Implement caching and BytesIO upload**

In `app.py`, add `import io` to the imports. After the `EMPTY_RESULT` definition, add:

```python
_cache = {"ids": None, "result": None}


def invalidate_cache():
    _cache["ids"] = None
    _cache["result"] = None
```

Change `compute_data` to:

```python
def compute_data(flagged_ids=None):
    if df is None:
        return EMPTY_RESULT
    ids = frozenset(flagged_ids or ())
    if _cache["result"] is not None and _cache["ids"] == ids:
        return _cache["result"]
    d = df.copy()
    flagged = set(flagged_ids or ())
    auto = auto_detect_knocked(d)
    merged = flagged | auto
    if merged:
        d["knocked"] = (d["tx_type"] == "BUY") & (d["transaction_id"].isin(merged))
    result = run_engine(d)
    _cache["ids"] = ids
    _cache["result"] = result
    return result
```

In `api_reload`, right after `df = parse_csv(str(CSV_PATH))` add:

```python
        invalidate_cache()
```

In `api_upload`, replace the temp-file block:

```python
        raw = f.read()
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb")
        tmp.write(raw)
        tmp.close()
        parsed = parse_csv(tmp.name)
```

with:

```python
        raw = f.read()
        parsed = parse_csv(io.BytesIO(raw))
```

and after `df = parsed` add:

```python
    invalidate_cache()
```

Also remove `import tempfile` from the imports and, in `api_knocked_down_toggle`, call `invalidate_cache()` after writing `KD_PATH` (the cache key changes anyway, but keep it explicit).

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 55 passed.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: cache engine results across API calls and parse uploads in memory"
```

---

## Self-Review Notes

- Spec coverage: review issues 1-8 map to Tasks 2, 3, 4, 6, 5, 7, 8, and 1/9 respectively (unmatched sells + MIGRATION = Tasks 1 and 4; dedup = Task 1; auto_detect sort = intentionally dropped, see below; TILG-only closed rows = Task 3; caching + temp file = Task 9; `abs()` on dividends = Task 6).
- Dropped from scope deliberately: `auto_detect_knocked` datetime sorting (the CSV export is chronological and the function only flags buys; low risk, and changing it has no observable effect on the current data). Revisit if a non-chronological export ever appears.
- Type consistency: `_empty_product` keys match the traded-product dict keys exactly; `total_dividend_tax`/`total_dividends_net` names are used identically in products, summary, by_asset_class, frontend columns, and tests.

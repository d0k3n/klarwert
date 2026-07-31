# Portfolio Analysis Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the features users expect from portfolio analysis: a FIFO audit trail, a tax report export, performance metrics (XIRR, win rate), unrealized P&L via manual prices, an income view, card spending analytics, and position concentration.

**Architecture:** New read-only computations live in new modules (`portfolio/performance.py`, `portfolio/tax_report.py`) or as new functions in `portfolio/engine.py`. The Flask app gains one endpoint per feature. The frontend gains one section per feature, reusing the existing table/chart patterns in `static/dashboard.js`. No new Python dependencies.

**Tech Stack:** Python 3, pandas, Flask, pytest (run with `py -m pytest`), vanilla JS, Chart.js (already vendored).

## Global Constraints

- REQUIRES the fixes plan `docs/superpowers/plans/2026-07-31-accounting-fixes.md` to be completed first. Tasks rely on: `total_dividend_tax`/`total_dividends_net` product and summary keys (fixes Task 6), `summary["reconciliation"]["cash_balance"]` (fixes Task 8), disposal-date semantics for knocked lots and TILG (fixes Tasks 2-3), and `app.invalidate_cache()` (fixes Task 9).
- Run tests with `py -m pytest tests -q` from the repo root. 55 tests pass after the fixes plan.
- Do not use em dashes ("—") in any file or commit message. Use commas, colons, or parentheses.
- Commit style follows repo history: lowercase conventional prefix, e.g. `feat: ...`.
- Test DataFrames may lack the `type`, `transaction_id`, and `knocked` columns. New engine code must tolerate that (guards and `row.get(...)`).
- API key names in existing responses must not be renamed. Only add new keys.
- Frontend has no test infrastructure: verify frontend tasks manually with the app running (steps included).

---

### Task 1: FIFO audit trail (lot matches)

**Files:**
- Modify: `portfolio/engine.py` (`Lot` dataclass, BUY/SELL/TILG/knocked branches, return dict)
- Modify: `app.py` (new endpoint)
- Modify: `templates/index.html` (new section)
- Modify: `static/dashboard.js` (fetch + table)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: the post-fixes engine (TILG disposal, short lots, knocked attribution).
- Produces: `run_engine(df)` result gains key `lot_matches`: list of dicts with keys `isin` (str), `name` (str), `sell_id` (str), `sell_datetime` (str, ISO), `lot_datetime` (str, ISO, may be `""`), `shares` (float), `proceeds` (float), `cost_basis` (float), `pl` (float). One row per (disposal event, lot) pair. Later tasks (tax report) consume this exact shape.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
def test_lot_matches_recorded_per_lot():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "S&P", "symbol": "SP",
         "asset_class": "FUND", "shares": 10.0, "price": 100.0, "amount": -1000.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "b1"},
        {"datetime": pd.Timestamp("2025-06-15", tz="UTC"), "tx_type": "BUY", "name": "S&P", "symbol": "SP",
         "asset_class": "FUND", "shares": 10.0, "price": 120.0, "amount": -1200.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "b2"},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "SELL", "name": "S&P", "symbol": "SP",
         "asset_class": "FUND", "shares": 15.0, "price": 130.0, "amount": 1950.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "s1"},
    ])
    result = run_engine(df)
    matches = result["lot_matches"]
    assert len(matches) == 2
    assert matches[0]["sell_id"] == "s1"
    assert matches[0]["shares"] == 10.0
    assert matches[0]["cost_basis"] == 1000.0
    assert matches[0]["proceeds"] == 1300.0
    assert matches[0]["pl"] == 300.0
    assert matches[0]["lot_datetime"].startswith("2025-06-01")
    assert matches[1]["shares"] == 5.0
    assert matches[1]["cost_basis"] == 600.0
    assert matches[1]["lot_datetime"].startswith("2025-06-15")


def test_lot_matches_for_knocked_and_tilg():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "W", "symbol": "DE200",
         "asset_class": "DERIVATIVE", "shares": 100.0, "price": 5.0, "amount": -500.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "b1", "knocked": True},
        {"datetime": pd.Timestamp("2025-06-20", tz="UTC"), "tx_type": "TILG", "name": "W", "symbol": "DE200",
         "asset_class": "DERIVATIVE", "shares": 0.0, "price": 0.0, "amount": 50.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "t1"},
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "Y", "symbol": "DE201",
         "asset_class": "DERIVATIVE", "shares": 10.0, "price": 10.0, "amount": -100.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "b2"},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "TILG", "name": "Y", "symbol": "DE201",
         "asset_class": "DERIVATIVE", "shares": 0.0, "price": 0.0, "amount": 30.0, "fee": 0.0, "tax": 0.0,
         "transaction_id": "t2"},
    ])
    result = run_engine(df)
    matches = result["lot_matches"]
    ko = [m for m in matches if m["isin"] == "DE200"]
    assert len(ko) == 1
    assert ko[0]["proceeds"] == 0.0
    assert ko[0]["pl"] == -500.0
    tilg = [m for m in matches if m["isin"] == "DE201"]
    assert len(tilg) == 1
    assert tilg[0]["proceeds"] == 30.0
    assert tilg[0]["cost_basis"] == 100.0
    assert tilg[0]["pl"] == -70.0
    assert tilg[0]["sell_id"] == "t2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_engine.py -q`
Expected: FAIL (KeyError: 'lot_matches').

- [ ] **Step 3: Implement lot match recording**

In `portfolio/engine.py`, extend the `Lot` dataclass:

```python
@dataclass
class Lot:
    id: int
    shares: float
    price: float
    total_cost: float
    datetime: object = None
```

In `run_engine`, after `per_product = {}` add:

```python
    lot_matches = []
```

Everywhere a BUY lot is appended, pass `datetime=row["datetime"]` (the normal BUY append and the short-lot append for unmatched sells).

In the knocked branch, after `cp["total_shares_sold"] += shares` add:

```python
                    lot_matches.append({
                        "isin": isin, "name": name, "sell_id": "",
                        "sell_datetime": ko_dt.isoformat(),
                        "lot_datetime": row["datetime"].isoformat(),
                        "shares": round(shares, 6),
                        "proceeds": 0.0,
                        "cost_basis": round(lot.total_cost, 2),
                        "pl": round(-lot.total_cost, 2),
                    })
```

In the short-cover while loop (BUY branch), after `cp["total_shares_sold"] += covered` add:

```python
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
```

In the SELL matching loop, replace:

```python
                    used = min(remaining, lot.shares)
                    ratio = used / lot.shares
                    sell_proceeds += used * price
                    cost_basis_total += lot.total_cost * ratio
                    lot.total_cost -= lot.total_cost * ratio
```

with:

```python
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
```

In the TILG disposal branch, replace `open_lots.clear()` with:

```python
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
```

Add to the return dict, after `"monthly_pl": ...`:

```python
        "lot_matches": lot_matches,
```

In `app.py`, add `lot_matches` to `EMPTY_RESULT` (value `[]`) and add the endpoint:

```python
@app.route("/api/lot_matches")
def api_lot_matches():
    return jsonify(compute_data(load_knocked_ids())["lot_matches"])
```

In `templates/index.html`, add a section before the Recent Transactions section:

```html
<section>
<h2>Sale Lot Matches (Audit Trail)</h2>
<div class="table-wrapper">
<table id="lot-matches-table">
<thead><tr>
<th data-sort="sell_datetime">Sold</th>
<th data-sort="name">Name</th>
<th data-sort="isin">ISIN</th>
<th data-sort="shares" class="num">Shares</th>
<th data-sort="proceeds" class="num">Proceeds</th>
<th data-sort="cost_basis" class="num">Cost Basis</th>
<th data-sort="pl" class="num">P&amp;L</th>
<th data-sort="lot_datetime">Acquired</th>
</tr></thead>
<tbody></tbody>
</table>
</div>
</section>
```

In `static/dashboard.js`:
- Add `lotMatches` to the `Promise.all` destructure and `loadJSON(`${BASE}/api/lot_matches`),` to the array.
- Add to `TABLE_CONFIGS`:

```javascript
  'lot-matches-table': {
    groupColumns: ['name', 'isin'],
    groupLabels: { name: 'Name', isin: 'ISIN' },
    numericFields: ['shares', 'proceeds', 'cost_basis', 'pl'],
  },
```

- Add `renderTable("lot-matches-table", lotMatches, TABLE_CONFIGS['lot-matches-table']);` after the derivative executions render call.
- In `formatVal`, add `|| key === 'proceeds' || key === 'cost_basis' || key === 'pl'` to the EUR condition, and handle the two datetime keys in `renderRows`: the existing `key === 'datetime'` branch handles only `datetime`; extend it to `key.endsWith('datetime')`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 57 passed.

- [ ] **Step 5: Verify the dashboard manually**

Run the app, open http://localhost:5000, confirm the audit table renders and that picking "Name" in its grouping dropdown totals proceeds/cost/P&L per product.

- [ ] **Step 6: Commit**

```bash
git add portfolio/engine.py app.py templates/index.html static/dashboard.js tests/test_engine.py
git commit -m "feat: FIFO audit trail with per-lot disposal matches"
```

---

### Task 2: Tax report (per fiscal year) with CSV download

**Files:**
- Create: `portfolio/tax_report.py`
- Modify: `app.py` (new endpoint)
- Modify: `templates/index.html` (new section)
- Modify: `static/dashboard.js` (render + CSV download)
- Test: `tests/test_tax_report.py` (new file)

**Interfaces:**
- Consumes: `run_engine(df)["lot_matches"]` (Task 1 shape), plus `df` cash rows for dividends/interest/saveback, and `app.compute_data` / `app.load_knocked_ids`.
- Produces: `build_tax_report(df, lot_matches, year) -> dict` with keys: `year` (int), `disposals` (list of dicts with `date`, `name`, `isin`, `shares`, `proceeds`, `cost_basis`, `fees`, `gain`, `acquired`), `disposal_totals` (`proceeds`, `cost_basis`, `fees`, `gain`), `dividends` (list of dicts with `date`, `name`, `isin`, `gross`, `wht`, `net`, `currency`), `dividend_totals` (`gross`, `wht`, `net`), `interest` (float), `saveback` (float). Endpoint: `GET /api/tax_report?year=YYYY`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tax_report.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_tax_report.py -q`
Expected: FAIL (ModuleNotFoundError: portfolio.tax_report).

- [ ] **Step 3: Implement the tax report module**

Create `portfolio/tax_report.py`:

```python
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
```

In `app.py`, add the import and endpoint:

```python
from portfolio.tax_report import build_tax_report
```

```python
@app.route("/api/tax_report")
def api_tax_report():
    if df is None:
        return jsonify({"year": None, "disposals": [], "disposal_totals": {},
                        "dividends": [], "dividend_totals": {}, "interest": 0.0, "saveback": 0.0})
    year = request.args.get("year", type=int)
    if not year:
        year = int(df["datetime"].max().year)
    result = compute_data(load_knocked_ids())
    return jsonify(build_tax_report(df, result["lot_matches"], year))
```

In `templates/index.html`, add a section after the audit trail section:

```html
<section>
<h2>Tax Report</h2>
<div>
  <label for="tax-year">Year:</label>
  <input type="number" id="tax-year" min="2000" max="2100" step="1">
  <button id="tax-report-btn" onclick="window.loadTaxReport()">Load</button>
  <button id="tax-csv-btn" onclick="window.downloadTaxCsv()">Download CSV</button>
</div>
<div class="table-wrapper">
<table id="tax-disposals-table">
<thead><tr>
<th data-sort="date">Date</th>
<th data-sort="name">Name</th>
<th data-sort="isin">ISIN</th>
<th data-sort="shares" class="num">Shares</th>
<th data-sort="proceeds" class="num">Proceeds</th>
<th data-sort="cost_basis" class="num">Cost Basis</th>
<th data-sort="fees" class="num">Fees</th>
<th data-sort="gain" class="num">Gain</th>
<th data-sort="acquired">Acquired</th>
</tr></thead>
<tbody></tbody>
</table>
</div>
<div class="table-wrapper">
<table id="tax-income-table">
<thead><tr><th>Type</th><th class="num">Gross</th><th class="num">WHT</th><th class="num">Net</th></tr></thead>
<tbody></tbody>
</table>
</div>
</section>
```

In `static/dashboard.js`, add:

```javascript
let lastTaxReport = null;

window.loadTaxReport = async function () {
const yearInput = document.getElementById("tax-year");
if (!yearInput.value) yearInput.value = new Date().getFullYear();
const report = await loadJSON(`${BASE}/api/tax_report?year=${yearInput.value}`);
lastTaxReport = report;
renderTable("tax-disposals-table", report.disposals, null);
const tbody = document.querySelector("#tax-income-table tbody");
tbody.innerHTML = "";
const eur = v => `\u20AC${(v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const t = report.dividend_totals;
[
  ["Dividends", t.gross, t.wht, t.net],
  ["Interest", report.interest, 0, report.interest],
  ["Saveback", report.saveback, 0, report.saveback],
].forEach(([label, g, w, n]) => {
  const tr = document.createElement("tr");
  tr.innerHTML = `<td>${label}</td><td class="num">${eur(g)}</td><td class="num">${eur(w)}</td><td class="num">${eur(n)}</td>`;
  tbody.appendChild(tr);
});
};

window.downloadTaxCsv = function () {
if (!lastTaxReport) return;
const lines = ["date;name;isin;shares;proceeds;cost_basis;fees;gain;acquired"];
lastTaxReport.disposals.forEach(d => {
  lines.push([d.date, d.name, d.isin, d.shares, d.proceeds, d.cost_basis, d.fees, d.gain, d.acquired].join(";"));
});
lines.push("");
lines.push("type;gross;wht;net");
lines.push(`dividends;${lastTaxReport.dividend_totals.gross};${lastTaxReport.dividend_totals.wht};${lastTaxReport.dividend_totals.net}`);
lines.push(`interest;${lastTaxReport.interest};;${lastTaxReport.interest}`);
const blob = new Blob([lines.join("\n")], { type: "text/csv" });
const a = document.createElement("a");
a.href = URL.createObjectURL(blob);
a.download = `tax_report_${lastTaxReport.year}.csv`;
a.click();
};
```

(`renderTable` with a `null` config renders plain rows without grouping, which the existing implementation already supports.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 60 passed.

- [ ] **Step 5: Verify against the real data**

Run the app, set the tax year to 2026, click Load, and cross-check one disposal against the audit trail table. Download the CSV and open it: disposals plus income totals.

- [ ] **Step 6: Commit**

```bash
git add portfolio/tax_report.py app.py templates/index.html static/dashboard.js tests/test_tax_report.py
git commit -m "feat: per-year tax report with disposal detail and CSV export"
```

---

### Task 3: Performance metrics (XIRR, win rate, averages)

**Files:**
- Create: `portfolio/performance.py`
- Modify: `app.py` (new endpoint)
- Modify: `static/dashboard.js` (new cards)
- Test: `tests/test_performance.py` (new file)

**Interfaces:**
- Consumes: `run_engine` result (uses `summary.reconciliation.cash_balance` from the fixes plan, `open_positions`, `closed_positions`).
- Produces: `xirr(flows) -> float | None` where `flows` is a list of `(pandas.Timestamp, float)`; `compute_performance(df, result) -> dict` with keys `xirr` (float or None), `terminal_value` (float), `winners` (int), `losers` (int), `win_rate` (float or None), `avg_win` (float or None), `avg_loss` (float or None). Endpoint: `GET /api/performance`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_performance.py`:

```python
import pandas as pd
from portfolio.engine import run_engine
from portfolio.performance import xirr, compute_performance


def test_xirr_single_flow_pair():
    flows = [
        (pd.Timestamp("2025-01-01", tz="UTC"), -1000.0),
        (pd.Timestamp("2026-01-01", tz="UTC"), 1100.0),
    ]
    r = xirr(flows)
    assert r is not None
    assert abs(r - 0.10) < 0.001


def test_xirr_no_sign_change_returns_none():
    flows = [
        (pd.Timestamp("2025-01-01", tz="UTC"), -1000.0),
        (pd.Timestamp("2025-06-01", tz="UTC"), -500.0),
    ]
    assert xirr(flows) is None


def test_compute_performance_win_stats():
    df = pd.DataFrame([
        {"datetime": pd.Timestamp("2025-01-01", tz="UTC"), "type": "TRANSFER_INSTANT_INBOUND",
         "tx_type": "DEPOSIT", "name": "", "symbol": "", "asset_class": "",
         "shares": 0.0, "price": 0.0, "amount": 3000.0, "fee": 0.0, "tax": 0.0, "transaction_id": "d1"},
        {"datetime": pd.Timestamp("2025-01-02", tz="UTC"), "type": "BUY", "tx_type": "BUY",
         "name": "W", "symbol": "W", "asset_class": "STOCK", "shares": 10.0, "price": 100.0,
         "amount": -1000.0, "fee": 0.0, "tax": 0.0, "transaction_id": "b1"},
        {"datetime": pd.Timestamp("2025-02-01", tz="UTC"), "type": "SELL", "tx_type": "SELL",
         "name": "W", "symbol": "W", "asset_class": "STOCK", "shares": 10.0, "price": 110.0,
         "amount": 1100.0, "fee": 0.0, "tax": 0.0, "transaction_id": "s1"},
        {"datetime": pd.Timestamp("2025-01-03", tz="UTC"), "type": "BUY", "tx_type": "BUY",
         "name": "L", "symbol": "L", "asset_class": "STOCK", "shares": 10.0, "price": 100.0,
         "amount": -1000.0, "fee": 0.0, "tax": 0.0, "transaction_id": "b2"},
        {"datetime": pd.Timestamp("2025-02-02", tz="UTC"), "type": "SELL", "tx_type": "SELL",
         "name": "L", "symbol": "L", "asset_class": "STOCK", "shares": 10.0, "price": 90.0,
         "amount": 900.0, "fee": 0.0, "tax": 0.0, "transaction_id": "s2"},
    ])
    result = run_engine(df)
    perf = compute_performance(df, result)
    assert perf["winners"] == 1
    assert perf["losers"] == 1
    assert perf["win_rate"] == 50.0
    assert perf["avg_win"] == 100.0
    assert perf["avg_loss"] == -100.0
    assert perf["terminal_value"] == 3000.0
    assert perf["xirr"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_performance.py -q`
Expected: FAIL (ModuleNotFoundError: portfolio.performance).

- [ ] **Step 3: Implement the performance module**

Create `portfolio/performance.py`:

```python
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
```

In `app.py`, add the import and endpoint:

```python
from portfolio.performance import compute_performance
```

```python
@app.route("/api/performance")
def api_performance():
    if df is None:
        return jsonify({})
    return jsonify(compute_performance(df, compute_data(load_knocked_ids())))
```

In `static/dashboard.js`, add `performance` to the `Promise.all` destructure (note: `performance` is a reserved browser global, use the name `perfData` for the variable) and `loadJSON(`${BASE}/api/performance`),` to the array. Then add after `renderSummary(summary);`:

```javascript
renderPerformance(perfData);
```

and the function:

```javascript
function renderPerformance(p) {
if (!p || Object.keys(p).length === 0) return;
const container = document.getElementById("summary-cards");
const eur = v => v == null ? "N/A" : `\u20AC${v.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const cards = [
  { label: "XIRR (annualized)", value: p.xirr == null ? "N/A" : `${(p.xirr * 100).toFixed(2)}%` },
  { label: "Win Rate (closed)", value: p.win_rate == null ? "N/A" : `${p.win_rate}% (${p.winners}W/${p.losers}L)` },
  { label: "Avg Win", value: eur(p.avg_win), cls: "positive" },
  { label: "Avg Loss", value: eur(p.avg_loss), cls: "negative" },
];
cards.forEach(c => {
  const div = document.createElement("div");
  div.className = "card";
  div.innerHTML = `<div class="label">${c.label}</div><div class="value ${c.cls || ""}">${c.value}</div>`;
  container.appendChild(div);
});
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 63 passed.

- [ ] **Step 5: Verify the dashboard manually**

Run the app and confirm the four new cards render and the XIRR value is plausible for the deposit history (between -100% and +100%).

- [ ] **Step 6: Commit**

```bash
git add portfolio/performance.py app.py static/dashboard.js tests/test_performance.py
git commit -m "feat: performance metrics (XIRR, win rate, average win/loss)"
```

---

### Task 4: Unrealized P&L via manual market prices

**Files:**
- Modify: `portfolio/engine.py` (new `apply_prices` function)
- Modify: `app.py` (prices storage, GET/POST endpoints, valued positions endpoint)
- Modify: `templates/index.html` (prices section, 3 new columns in open positions table)
- Modify: `static/dashboard.js` (valued positions fetch, price inputs, new cards)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `open_positions` from `run_engine`, `app.invalidate_cache()` from the fixes plan.
- Produces: `apply_prices(open_positions, prices) -> dict` with keys `positions` (each original position plus `market_price` (float or None), `market_value` (float or None), `unrealized_pl` (float or None)) and `totals` (`market_value`, `unrealized_pl`, summed over priced positions only). Endpoints: `GET /api/prices` -> `{isin: price}`, `POST /api/prices` body `{"isin": "...", "price": 123.45}` (null price deletes), `GET /api/valued_positions` -> the `apply_prices` dict.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py` (extend the import to include `apply_prices`):

```python
def test_apply_prices_computes_unrealized():
    positions = [
        {"isin": "A", "name": "A", "asset_class": "STOCK", "shares": 10.0,
         "average_cost": 50.0, "total_cost": 500.0},
        {"isin": "B", "name": "B", "asset_class": "FUND", "shares": 5.0,
         "average_cost": 100.0, "total_cost": 500.0},
    ]
    valued = apply_prices(positions, {"A": 60.0})
    a, b = valued["positions"]
    assert a["market_price"] == 60.0
    assert a["market_value"] == 600.0
    assert a["unrealized_pl"] == 100.0
    assert b["market_price"] is None
    assert b["market_value"] is None
    assert b["unrealized_pl"] is None
    assert valued["totals"]["market_value"] == 600.0
    assert valued["totals"]["unrealized_pl"] == 100.0


def test_apply_prices_empty_prices():
    valued = apply_prices([{"isin": "A", "name": "A", "asset_class": "STOCK",
                            "shares": 1.0, "average_cost": 10.0, "total_cost": 10.0}], {})
    assert valued["totals"]["market_value"] == 0.0
    assert valued["positions"][0]["market_price"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_engine.py -q`
Expected: FAIL (ImportError: cannot import name 'apply_prices').

- [ ] **Step 3: Implement prices storage and valued positions**

In `portfolio/engine.py`, add at module level:

```python
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
```

In `app.py`, after the `KD_PATH` definition add:

```python
PRICES_PATH = BASE_DIR / "prices.json"


def load_prices():
    if PRICES_PATH.exists():
        return {k: float(v) for k, v in json.loads(PRICES_PATH.read_text(encoding="utf-8")).items()}
    return {}


def save_prices(prices):
    PRICES_PATH.write_text(json.dumps(prices, indent=2), encoding="utf-8")
```

Add the endpoints:

```python
@app.route("/api/prices", methods=["GET"])
def api_prices_get():
    return jsonify(load_prices())


@app.route("/api/prices", methods=["POST"])
def api_prices_post():
    body = request.get_json(silent=True) or {}
    isin = (body.get("isin") or "").strip()
    if not isin:
        return jsonify({"ok": False, "error": "missing isin"}), 400
    prices = load_prices()
    price = body.get("price")
    if price is None:
        prices.pop(isin, None)
    else:
        prices[isin] = float(price)
    save_prices(prices)
    return jsonify({"ok": True, "prices": prices})


@app.route("/api/valued_positions")
def api_valued_positions():
    result = compute_data(load_knocked_ids())
    return jsonify(apply_prices(result["open_positions"], load_prices()))
```

Add `apply_prices` to the engine import line in `app.py`.

In `templates/index.html`, add three columns to the open positions table thead, after Total Cost:

```html
<th data-sort="market_price" class="num">Mkt Price</th>
<th data-sort="market_value" class="num">Mkt Value</th>
<th data-sort="unrealized_pl" class="num">Unreal. P&amp;L</th>
```

and add a prices input section right before the Open Positions section:

```html
<section>
  <h2>Market Prices (manual)</h2>
  <p>Enter a current price per ISIN to see market value and unrealized P&amp;L. Leave empty to clear.</p>
  <div id="price-inputs"></div>
</section>
```

In `static/dashboard.js`:
- Replace `loadJSON(`${BASE}/api/open_positions`),` with `loadJSON(`${BASE}/api/valued_positions`),` and rename the destructured variable to `valuedPositions`.
- Replace the open positions render call with:

```javascript
const openPositions = valuedPositions.positions || [];
renderTable("open-positions-table", openPositions, TABLE_CONFIGS['open-positions-table']);
renderPriceInputs(openPositions);
renderValuedCards(valuedPositions.totals || {});
```

(remove the old `renderTable("open-positions-table", openPositions, ...)` line and keep `renderAllocationChart(openPositions);` as is.)
- In `TABLE_CONFIGS['open-positions-table'].numericFields`, add `'market_value', 'unrealized_pl'`; in `averageFields` add `'market_price'`.
- In `formatVal`, add `|| key === 'market_value' || key === 'unrealized_pl' || key === 'market_price'` to the EUR condition.
- Add the new functions:

```javascript
function renderValuedCards(totals) {
const container = document.getElementById("summary-cards");
const eur = v => `\u20AC${(v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
[
  { label: "Est. Market Value", value: eur(totals.market_value) },
  { label: "Unrealized P&L", value: eur(totals.unrealized_pl), cls: (totals.unrealized_pl || 0) >= 0 ? "positive" : "negative" },
].forEach(c => {
  const div = document.createElement("div");
  div.className = "card";
  div.innerHTML = `<div class="label">${c.label}</div><div class="value ${c.cls || ""}">${c.value}</div>`;
  container.appendChild(div);
});
}

function renderPriceInputs(positions) {
const container = document.getElementById("price-inputs");
container.innerHTML = "";
positions.forEach(p => {
  const row = document.createElement("div");
  row.style.marginBottom = "6px";
  row.innerHTML = `<span style="display:inline-block; width:320px;">${p.name} (${p.isin})</span>`;
  const input = document.createElement("input");
  input.type = "number";
  input.step = "0.0001";
  input.min = "0";
  input.placeholder = "price";
  if (p.market_price != null) input.value = p.market_price;
  input.addEventListener("change", async () => {
    const price = input.value === "" ? null : parseFloat(input.value);
    await fetch(`${BASE}/api/prices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isin: p.isin, price }),
    });
    await loadAllData();
  });
  row.appendChild(input);
  container.appendChild(row);
});
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 65 passed.

- [ ] **Step 5: Verify the dashboard manually**

Run the app, enter a price for one open position, confirm the Mkt Value and Unreal. P&L columns fill in, the two new summary cards appear, and the value survives a page reload (stored in `prices.json`).

- [ ] **Step 6: Commit**

```bash
git add portfolio/engine.py app.py templates/index.html static/dashboard.js tests/test_engine.py
git commit -m "feat: unrealized P&L from manually entered market prices"
```

---

### Task 5: Income view (monthly income, dividend history, yield on cost)

**Files:**
- Modify: `portfolio/engine.py` (new `compute_income`, `yield_on_cost` on products)
- Modify: `app.py` (new endpoint)
- Modify: `templates/index.html` (new section, products table column)
- Modify: `static/dashboard.js` (income chart + history table)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `total_dividends_net` per product (fixes plan), open positions cost from `run_engine`.
- Produces: `compute_income(df) -> {"monthly": [{"month", "dividends", "interest", "saveback", "total"}], "dividends": [{"date", "name", "isin", "gross", "wht", "net", "currency"}]}`. Products gain key `yield_on_cost` (float percent or None). Endpoint: `GET /api/income` returns the `compute_income` dict.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py` (extend the import to include `compute_income`):

```python
def test_compute_income_monthly_and_history():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-15", tz="UTC"), "tx_type": "DIVIDEND", "name": "ABC", "symbol": "US1",
         "asset_class": "STOCK", "shares": 0.0, "price": 0.0, "amount": 10.0, "fee": 0.0, "tax": -1.5,
         "currency": "EUR", "original_currency": "USD"},
        {"datetime": pd.Timestamp("2025-06-20", tz="UTC"), "tx_type": "INTEREST", "name": "", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 2.0, "fee": 0.0, "tax": 0.0,
         "currency": "EUR", "original_currency": ""},
        {"datetime": pd.Timestamp("2025-07-02", tz="UTC"), "tx_type": "SAVEBACK", "name": "S&P", "symbol": "IE",
         "asset_class": "FUND", "shares": 0.0, "price": 0.0, "amount": 3.0, "fee": 0.0, "tax": 0.0,
         "currency": "EUR", "original_currency": ""},
    ])
    income = compute_income(df)
    jun = [m for m in income["monthly"] if m["month"] == "2025-06"][0]
    assert jun["dividends"] == 8.5
    assert jun["interest"] == 2.0
    assert jun["total"] == 10.5
    jul = [m for m in income["monthly"] if m["month"] == "2025-07"][0]
    assert jul["saveback"] == 3.0
    assert len(income["dividends"]) == 1
    d = income["dividends"][0]
    assert d["gross"] == 10.0
    assert d["wht"] == 1.5
    assert d["net"] == 8.5
    assert d["currency"] == "USD"


def test_yield_on_cost_for_open_product():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "ABC", "symbol": "US1",
         "asset_class": "STOCK", "shares": 10.0, "price": 100.0, "amount": -1000.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-07-01", tz="UTC"), "tx_type": "DIVIDEND", "name": "ABC", "symbol": "US1",
         "asset_class": "STOCK", "shares": 0.0, "price": 0.0, "amount": 25.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    p = result["products"][0]
    assert p["yield_on_cost"] == 2.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_engine.py -q`
Expected: FAIL (no `compute_income`, no `yield_on_cost`).

- [ ] **Step 3: Implement income computation**

In `portfolio/engine.py`, add:

```python
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
```

In `run_engine`, after the dividend rounding loop (`for isin in per_product: ...`), add:

```python
    open_cost_by_isin = {p["isin"]: p["total_cost"] for p in open_positions}
    for isin, p in per_product.items():
        cost = open_cost_by_isin.get(isin)
        if cost and cost > 0:
            p["yield_on_cost"] = round(100 * p["total_dividends_net"] / cost, 2)
        else:
            p["yield_on_cost"] = None
```

In `app.py`, add `compute_income` to the engine import and the endpoint:

```python
@app.route("/api/income")
def api_income():
    if df is None:
        return jsonify({"monthly": [], "dividends": []})
    return jsonify(compute_income(df))
```

In `templates/index.html`, add a `Yield %` column to the products table (after Div. WHT):

```html
      <th data-sort="yield_on_cost" class="num">Yield %</th>
```

and add a new section after the Product Charts section:

```html
<section>
  <h2>Income</h2>
  <canvas id="income-chart"></canvas>
  <h3>Dividend History</h3>
  <div class="table-wrapper">
  <table id="dividend-history-table">
  <thead><tr>
  <th data-sort="date">Date</th>
  <th data-sort="name">Name</th>
  <th data-sort="isin">ISIN</th>
  <th data-sort="gross" class="num">Gross</th>
  <th data-sort="wht" class="num">WHT</th>
  <th data-sort="net" class="num">Net</th>
  <th data-sort="currency">Ccy</th>
  </tr></thead>
  <tbody></tbody>
  </table>
  </div>
</section>
```

In `static/dashboard.js`:
- Add `income` to the `Promise.all` destructure and `loadJSON(`${BASE}/api/income`),` to the array.
- Add `'yield_on_cost'` to `TABLE_CONFIGS['product-results-table'].numericFields`... actually it must NOT be summed (it is a ratio): add it to `averageFields` instead: `averageFields: ['yield_on_cost']`. In `formatVal`, add at the top of the numeric branch:

```javascript
  if (key === 'yield_on_cost') return val == null ? '' : `${val.toFixed(2)}%`;
```

- Add render calls after `renderDividendChart(products);`:

```javascript
renderIncomeChart(income.monthly);
renderTable("dividend-history-table", income.dividends, null);
```

- Add the chart function (and `let incomeChart = null;` next to the other chart globals):

```javascript
function renderIncomeChart(monthly) {
  if (incomeChart) incomeChart.destroy();
  const ctx = document.getElementById("income-chart").getContext("2d");
  incomeChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: monthly.map(d => d.month),
      datasets: [
        { label: "Dividends (net)", data: monthly.map(d => d.dividends), backgroundColor: "#bc8cff" },
        { label: "Interest", data: monthly.map(d => d.interest), backgroundColor: "#7ee787" },
        { label: "Saveback", data: monthly.map(d => d.saveback), backgroundColor: "#58a6ff" },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: "top", labels: { color: "#8b949e" } },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
      scales: {
        x: { stacked: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
        y: { stacked: true, beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
      },
    },
  });
}
```

- In `formatVal`, add `|| key === 'gross' || key === 'wht' || key === 'net'` to the EUR condition for the history table.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 67 passed.

- [ ] **Step 5: Verify the dashboard manually**

Run the app: the Income chart should show stacked monthly bars, the dividend history lists the ASML/Novo/Alphabet payments with WHT, and the products table shows Yield % for open positions with dividends.

- [ ] **Step 6: Commit**

```bash
git add portfolio/engine.py app.py templates/index.html static/dashboard.js tests/test_engine.py
git commit -m "feat: income view with monthly chart, dividend history, yield on cost"
```

---

### Task 6: Card spending analytics by MCC category

**Files:**
- Modify: `portfolio/engine.py` (new `compute_spending`)
- Modify: `app.py` (new endpoint)
- Modify: `templates/index.html` (new section)
- Modify: `static/dashboard.js` (doughnut + monthly bar)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: parsed `df` (CARD rows carry `mcc_code` from the CSV).
- Produces: `compute_spending(df) -> {"by_category": [{"category", "total"}], "monthly": [{"month", "total"}]}`, totals as positive floats (refunds net against their category). Endpoint: `GET /api/spending`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py` (extend the import to include `compute_spending`):

```python
def test_compute_spending_categories_and_refunds():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "CARD", "name": "INTERMARCHE", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": -50.0, "fee": 0.0, "tax": 0.0,
         "mcc_code": "5411"},
        {"datetime": pd.Timestamp("2025-06-02", tz="UTC"), "tx_type": "CARD", "name": "RESTAURANT", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": -30.0, "fee": 0.0, "tax": 0.0,
         "mcc_code": "5812"},
        {"datetime": pd.Timestamp("2025-06-03", tz="UTC"), "tx_type": "CARD", "name": "INTERMARCHE", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": 10.0, "fee": 0.0, "tax": 0.0,
         "mcc_code": "5411"},
        {"datetime": pd.Timestamp("2025-06-04", tz="UTC"), "tx_type": "CARD", "name": "UNKNOWN SHOP", "symbol": "",
         "asset_class": "", "shares": 0.0, "price": 0.0, "amount": -5.0, "fee": 0.0, "tax": 0.0,
         "mcc_code": ""},
    ])
    spending = compute_spending(df)
    by_cat = {c["category"]: c["total"] for c in spending["by_category"]}
    assert by_cat["Groceries"] == 40.0
    assert by_cat["Restaurants"] == 30.0
    assert by_cat["Other"] == 5.0
    jun = [m for m in spending["monthly"] if m["month"] == "2025-06"][0]
    assert jun["total"] == 75.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_engine.py -q`
Expected: FAIL (ImportError: cannot import name 'compute_spending').

- [ ] **Step 3: Implement spending analytics**

In `portfolio/engine.py`, add:

```python
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
```

In `app.py`, add `compute_spending` to the engine import and the endpoint:

```python
@app.route("/api/spending")
def api_spending():
    if df is None:
        return jsonify({"by_category": [], "monthly": []})
    return jsonify(compute_spending(df))
```

In `templates/index.html`, replace the Card Expenses section content with (keep the existing merchant table below the new charts):

```html
<section>
<h2>Card Spending</h2>
<canvas id="spending-category-chart"></canvas>
<canvas id="spending-monthly-chart"></canvas>
<div class="table-wrapper">
<table id="card-expenses-table">
<thead><tr>
<th data-sort="datetime">Date</th>
<th data-sort="name">Merchant</th>
<th data-sort="amount" class="num">Amount</th>
<th data-sort="description">Description</th>
</tr></thead>
<tbody></tbody>
</table>
</div>
</section>
```

In `static/dashboard.js`:
- Add `spending` to the `Promise.all` destructure and `loadJSON(`${BASE}/api/spending`),` to the array.
- Add `let spendingCatChart = null;` and `let spendingMonthChart = null;` next to the other chart globals.
- Add after the card-expenses render call:

```javascript
renderSpendingCharts(spending);
```

- Add the functions:

```javascript
function renderSpendingCharts(spending) {
  if (spendingCatChart) spendingCatChart.destroy();
  const catCtx = document.getElementById("spending-category-chart").getContext("2d");
  const cats = spending.by_category || [];
  spendingCatChart = new Chart(catCtx, {
    type: "doughnut",
    data: {
      labels: cats.map(c => c.category),
      datasets: [{
        data: cats.map(c => c.total),
        backgroundColor: cats.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: "right", labels: { color: "#8b949e" } },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
    },
  });
  if (spendingMonthChart) spendingMonthChart.destroy();
  const monCtx = document.getElementById("spending-monthly-chart").getContext("2d");
  const months = spending.monthly || [];
  spendingMonthChart = new Chart(monCtx, {
    type: "bar",
    data: {
      labels: months.map(m => m.month),
      datasets: [{ label: "Card Spending", data: months.map(m => m.total), backgroundColor: CHART_BLUE }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
      scales: {
        x: { ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
        y: { beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
      },
    },
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 68 passed.

- [ ] **Step 5: Verify the dashboard manually**

Run the app: the spending doughnut should show Groceries/Restaurants/etc. from the real MCC codes, with an Other slice for rows without MCC (the international subscriptions).

- [ ] **Step 6: Commit**

```bash
git add portfolio/engine.py app.py templates/index.html static/dashboard.js tests/test_engine.py
git commit -m "feat: card spending analytics by MCC category"
```

---

### Task 7: Position weights and top-5 concentration

**Files:**
- Modify: `portfolio/engine.py` (open positions block)
- Modify: `templates/index.html` (open positions table column)
- Modify: `static/dashboard.js` (weight formatting, concentration card)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `open_positions` from `run_engine`.
- Produces: each open position gains key `weight` (float, fraction of total positive open cost, 4 decimals; 0.0 for negative/short positions or when total is 0).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine.py`:

```python
def test_open_position_weights():
    df = _make_df([
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "A", "symbol": "A",
         "asset_class": "STOCK", "shares": 10.0, "price": 30.0, "amount": -300.0, "fee": 0.0, "tax": 0.0},
        {"datetime": pd.Timestamp("2025-06-01", tz="UTC"), "tx_type": "BUY", "name": "B", "symbol": "B",
         "asset_class": "STOCK", "shares": 10.0, "price": 10.0, "amount": -100.0, "fee": 0.0, "tax": 0.0},
    ])
    result = run_engine(df)
    weights = {p["symbol"]: p["weight"] for p in result["open_positions"]}
    assert weights["A"] == 0.75
    assert weights["B"] == 0.25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_engine.py::test_open_position_weights -q`
Expected: FAIL (KeyError: 'weight').

- [ ] **Step 3: Implement weights**

In `portfolio/engine.py`, in `run_engine`, replace the open positions return preparation. After the per-ISIN loop (before the dividend block), add:

```python
    total_open_cost = sum(p["total_cost"] for p in open_positions if p["total_cost"] > 0)
    for p in open_positions:
        if total_open_cost > 0 and p["total_cost"] > 0:
            p["weight"] = round(p["total_cost"] / total_open_cost, 4)
        else:
            p["weight"] = 0.0
```

In `templates/index.html`, add to the open positions table thead, after Unreal. P&L:

```html
<th data-sort="weight" class="num">Weight</th>
```

In `static/dashboard.js`:
- In `TABLE_CONFIGS['open-positions-table'].numericFields`, add `'weight'`.
- In `formatVal`, at the top of the numeric branch add:

```javascript
  if (key === 'weight') return `${(val * 100).toFixed(1)}%`;
```

- In `renderValuedCards` (Task 4), add a third card computed from positions. Change its signature to `renderValuedCards(totals, positions)` and update the call site. Add inside the function, before the `forEach`:

```javascript
const top5 = (positions || [])
  .map(p => p.weight || 0)
  .sort((a, b) => b - a)
  .slice(0, 5)
  .reduce((a, b) => a + b, 0);
```

and add to its cards array:

```javascript
  { label: "Top 5 Concentration", value: `${(top5 * 100).toFixed(1)}%` },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests -q`
Expected: 69 passed.

- [ ] **Step 5: Verify the dashboard manually**

Run the app: the Weight column shows percentages summing to 100%, and the Top 5 Concentration card appears in the summary cards.

- [ ] **Step 6: Commit**

```bash
git add portfolio/engine.py templates/index.html static/dashboard.js tests/test_engine.py
git commit -m "feat: position weights and top-5 concentration card"
```

---

## Self-Review Notes

- Spec coverage: all seven suggested features map to Tasks 1-7 (audit trail, tax report, performance, unrealized P&L, income, spending, concentration).
- Dependency order: Task 2 requires Task 1 (`lot_matches`). Task 7 amends Task 4's `renderValuedCards`. Task 5 requires the fixes plan's dividend WHT fields. Everything else is independent.
- Type consistency: `lot_matches` keys are used identically in engine, tax report, and frontend columns (`sell_datetime`, `lot_datetime`, `shares`, `proceeds`, `cost_basis`, `pl`). `apply_prices` keys (`market_price`, `market_value`, `unrealized_pl`) match the table headers and `formatVal`. `compute_performance` keys match `renderPerformance`.
- Deliberately out of scope: live market data APIs, benchmark overlays, multi-currency portfolios (all data is EUR). These need external data sources and are noted in the original spec as future extensions.

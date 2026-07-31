# Derivative Executions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Add a dedicated table for derivative products showing KO losses and warrant returns, reconciled by product name and quantity.

**Architecture:** New backend function `compute_derivative_executions()` in engine.py groups derivative transactions by ISIN. New API endpoint returns the data. New JS renderer + HTML section displays it.

**Tech Stack:** Python 3 (Flask + pandas), vanilla JS + Chart.js

## Global Constraints

- Transactions CSV has columns: transaction_id, datetime, type, category, asset_class, name, symbol, shares, price, amount, fee
- KO'd BUYs are flagged via `knocked_down.json` by transaction_id
- WARRANT_EXERCISE type is classified as SELL in parser.py
- TILG type is classified as TILG in parser.py
- Follow existing code style (no added comments)

---

### Task 1: Backend — engine function

**Files:**
- Modify: `portfolio/engine.py` (add function)
- Test: none

**Interfaces:**
- Produces: `compute_derivative_executions(df, knocked_ids)` → list of dicts with keys: `name`, `isin`, `asset_class`, `ko_quantity`, `ko_loss`, `ko_fees`, `ko_total`, `warrant_quantity`, `warrant_return`, `net_result`, `reconciled`

- [ ] **Add `compute_derivative_executions()` to engine.py**

After `run_engine()`, add function that:
1. Filters rows where `asset_class == "DERIVATIVE"`
2. Separates into BUY (with knocked flag), WARRANT_EXERCISE, and TILG rows
3. Groups by `symbol` (ISIN)
4. For each ISIN: sum KO'd shares/cost, sum warrant exercise shares, sum TILG amounts
5. Returns list of dicts sorted by name

```python
def compute_derivative_executions(df, knocked_ids):
    deriv = df[df["asset_class"] == "DERIVATIVE"].copy()
    if deriv.empty:
        return []

    buys = deriv[deriv["tx_type"] == "BUY"]
    warrant_ex = deriv[deriv["type"] == "WARRANT_EXERCISE"]
    tilg = deriv[deriv["tx_type"] == "TILG"]

    by_isin: dict[str, dict] = {}

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
        entry["ko_loss"] = round(entry["ko_loss"], 2)
        entry["ko_fees"] = round(entry["ko_fees"], 2)
        entry["ko_total"] = round(entry["ko_loss"] + entry["ko_fees"], 2)
        entry["warrant_return"] = round(entry["warrant_return"], 2)
        entry["net_result"] = round(entry["ko_total"] + entry["warrant_return"], 2)
        entry["reconciled"] = abs(entry["ko_quantity"] - entry["warrant_quantity"]) < 0.01
        result.append(entry)

    return sorted(result, key=lambda x: x["name"])
```

- [ ] **Step — Verify syntax**

Run: `python -c "from portfolio.engine import compute_derivative_executions; print('OK')"`

### Task 2: Backend — API endpoint

**Files:**
- Modify: `app.py`

- [ ] **Add `/api/derivative_executions` endpoint**

```python
@app.route("/api/derivative_executions")
def api_derivative_executions():
    data = compute_data(load_knocked_ids())
    return jsonify(compute_derivative_executions(df, load_knocked_ids()))
```

- [ ] **Verify app starts**

Run: `python app.py` for 5s, confirm no import errors.

### Task 3: Frontend — HTML section

**Files:**
- Modify: `templates/index.html`

- [ ] **Add derivative executions section** after the product results table (before `#product-charts`)

```html
<section>
  <h2>Derivative Executions</h2>
  <table id="derivative-executions-table">
    <thead><tr>
      <th data-sort="name">Name</th>
      <th data-sort="isin">ISIN</th>
      <th data-sort="ko_quantity" class="num">KO'd Qty</th>
      <th data-sort="ko_total" class="num">KO Loss</th>
      <th data-sort="warrant_return" class="num">Warrant Return</th>
      <th data-sort="net_result" class="num">Net Result</th>
      <th data-sort="reconciled">Reconciled?</th>
    </tr></thead>
    <tbody></tbody>
  </table>
</section>
```

### Task 4: Frontend — JS renderer

**Files:**
- Modify: `static/dashboard.js`

- [ ] **Add `renderDerivativeExecutions()` function**

Call from `loadAllData()` after `renderDividendChart`:

```javascript
renderDerivativeExecutions(await loadJSON(`${BASE}/api/derivative_executions`));
```

Render function:

```javascript
function renderDerivativeExecutions(data) {
  const table = document.getElementById("derivative-executions-table");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  data.forEach(row => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.name}</td>
      <td>${row.isin}</td>
      <td class="num">${row.ko_quantity.toLocaleString()}</td>
      <td class="num ${row.ko_total < 0 ? 'negative' : ''}">€${row.ko_total.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td class="num positive">€${row.warrant_return.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td class="num ${row.net_result < 0 ? 'negative' : 'positive'}">€${row.net_result.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
      <td>${row.reconciled ? '✓' : '✗'}</td>
    `;
    tbody.appendChild(tr);
  });
}
```

### Task 5: Verify

- [ ] Start app, open browser, confirm new table renders with correct data

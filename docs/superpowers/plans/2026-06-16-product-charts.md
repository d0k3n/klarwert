# Product Charts & Results — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-product aggregated results, monthly realized P&L chart, allocation chart, and dividend charts to the portfolio dashboard.

**Architecture:** Extend `run_engine()` to compute two new dicts (`per_product`, `monthly_pl`), expose them via new Flask routes, then render with Chart.js in the frontend.

**Tech Stack:** Python/Flask, JavaScript/Chart.js, HTML/CSS

---

### Task 1: Extend engine.py — `per_product` and `monthly_pl`

**Files:**
- Modify: `portfolio/engine.py`

- [ ] **Step 1: Add `monthly_pl` and `per_product` computation inside `run_engine()`**

Insert right after the `by_isin` defaultdict initialization (line 24 in current file), add monthly tracking:

```python
    monthly_pl = defaultdict(float)
    per_product = {}
```

Inside the `for isin, rows in by_isin.items():` loop, initialize product tracking right after getting `name`:

```python
        name = rows[0]["name"]
        total_invested = 0.0
        total_fees = 0.0
        total_trades = 0
```

Add to `total_invested` in the BUY branch:

```python
            if row["tx_type"] == "BUY":
                total_invested += shares * price
                total_fees += abs(row["fee"]) if not _isna(row["fee"]) else 0.0
                total_trades += 1
                open_lots.append(Lot(...))
```

Add to `total_fees` and `total_trades` in the SELL branch:

```python
            elif row["tx_type"] == "SELL":
                total_fees += abs(row["fee"]) if not _isna(row["fee"]) else 0.0
                total_trades += 1
                remaining = shares
```

After computing `realized_pl` in the SELL branch, capture monthly P&L:

```python
                realized_pl = sell_proceeds - cost_basis_total
                month = row["datetime"].strftime("%Y-%m")
                monthly_pl[month] += realized_pl
```

After the inner loop (inside the ISIN loop but after the `for row in rows:` block), add per-product data. Use the accumulated `total_invested`, `total_fees`, and `total_trades` variables + `monthly_pl` from the SELL branch:

```python
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
```

Note: `closed_positions` is a `defaultdict` with default `total_realized_pl: 0.0`, so accessing it for a never-sold ISIN returns 0.0 — no special check needed.

Then, after all ISINs are processed, aggregate dividends per ISIN from cash_rows:

```python
    # Aggregate dividends per ISIN
    div_rows = cash_rows[cash_rows["tx_type"] == "DIVIDEND"]
    for _, row in div_rows.iterrows():
        isin = row["symbol"]
        if isin in per_product:
            per_product[isin]["total_dividends"] += abs(row["amount"])
    for isin in per_product:
        per_product[isin]["total_dividends"] = round(per_product[isin]["total_dividends"], 2)
```

Finally, after the cash_flow computation, add to the return dict:

```python
    return {
        "summary": summary,
        "open_positions": open_positions,
        "closed_positions": list(closed_positions.values()),
        "cash_flow": cash_flow,
        "transactions": transactions,
        "products": list(per_product.values()),
        "monthly_pl": [{"month": m, "realized_pl": round(v, 2)} for m, v in sorted(monthly_pl.items())],
    }
```

- [ ] **Step 2: Run the app to verify no errors**

Run: `cd C:\git\Pessoal\traderepublic && python -c "from portfolio.engine import run_engine; from portfolio.parser import parse_csv; df = parse_csv('transactions.csv'); result = run_engine(df); print('products:', len(result['products'])); print('monthly_pl:', len(result['monthly_pl']))"`

---

### Task 2: Add API routes in app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add two new routes after the existing routes (before the knocked_down routes)**

```python
@app.route("/api/products")
def api_products():
    return jsonify(compute_data(load_knocked_ids())["products"])


@app.route("/api/monthly_pl")
def api_monthly_pl():
    return jsonify(compute_data(load_knocked_ids())["monthly_pl"])
```

- [ ] **Step 2: Restart and test routes**

Run: `python -c "import requests; r = requests.get('http://localhost:5000/api/products'); print(r.status_code, len(r.json()))"`

---

### Task 3: Update index.html with new sections

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add monthly P&L chart section after summary cards and before open positions**

After `<section id="summary-cards" class="cards"></section>` and before `<section>` with open positions:

```html
<section>
  <h2>Monthly Realized P&amp;L</h2>
  <canvas id="monthly-pl-chart" height="250"></canvas>
</section>
```

- [ ] **Step 2: Add product results table after closed positions**

After `</section>` closing closed-positions and before the Cash Flow section:

```html
<section>
  <h2>Results by Product</h2>
  <table id="product-results-table">
    <thead><tr>
      <th data-sort="name">Name</th>
      <th data-sort="isin">ISIN</th>
      <th data-sort="asset_class">Asset Class</th>
      <th data-sort="status">Status</th>
      <th data-sort="total_invested" class="num">Invested</th>
      <th data-sort="total_realized_pl" class="num">Realized P&amp;L</th>
      <th data-sort="total_dividends" class="num">Dividends</th>
      <th data-sort="total_fees" class="num">Fees</th>
      <th data-sort="total_trades" class="num">Trades</th>
    </tr></thead>
    <tbody></tbody>
  </table>
</section>
```

- [ ] **Step 3: Add product charts section (allocation + dividends) after product table**

After the product results table section and before Cash Flow section:

```html
<section id="product-charts">
  <h2>Product Charts</h2>
  <div style="display:flex; gap:24px; flex-wrap:wrap;">
    <div style="flex:1; min-width:300px;">
      <h3>Allocation by Product</h3>
      <canvas id="allocation-chart" height="300"></canvas>
    </div>
    <div style="flex:1; min-width:300px;">
      <h3>Dividends by Product</h3>
      <canvas id="dividend-chart" height="300"></canvas>
    </div>
  </div>
</section>
```

---

### Task 4: Implement rendering in dashboard.js

**Files:**
- Modify: `static/dashboard.js`

- [ ] **Step 1: Fetch new API endpoints**

In the Promise.all, add:

```javascript
const [summary, openPositions, closedPositions, cashFlow, transactions, knockedDown, products, monthlyPl] = await Promise.all([
  ...
  loadJSON(`${BASE}/api/products`),
  loadJSON(`${BASE}/api/monthly_pl`),
]);
```

Add rendering calls after `renderCashFlowChart(cashFlow);`:

```javascript
renderMonthlyPLChart(monthlyPl);
renderProductTable(products);
renderAllocationChart(products);
renderDividendChart(products);
```

- [ ] **Step 2: Add renderMonthlyPLChart function**

```javascript
function renderMonthlyPLChart(data) {
  const ctx = document.getElementById("monthly-pl-chart").getContext("2d");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map(d => d.month),
      datasets: [{
        label: "Realized P&L",
        data: data.map(d => d.realized_pl),
        backgroundColor: data.map(d => d.realized_pl >= 0 ? "#16a34a" : "#dc2626"),
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true } },
    },
  });
}
```

- [ ] **Step 3: Add renderProductTable function**

The product table uses the same sorting logic as `renderTable`. Since `renderTable` is already generic enough, we can either refactor it or add the product-specific rendering. Let's keep it simple and call `renderTable` with the product data:

```javascript
renderTable("product-results-table", products);
```

But the renderTable function needs to handle the new columns. Looking at the existing code, `renderTable` already works generically: it reads `th.dataset.sort` for each column header and renders `row[key]`. For the product columns, the numeric formatting should apply too. We need to update the number formatting logic in `renderTable` to handle the new column names.

Actually, `renderTable` checks for specific keys:
- `average_cost`, `total_cost`, `total_realized_pl` → € with 2 decimals
- `shares`, `total_shares_sold` → 4 decimals
- Others → default toLocaleString

For the product table, `total_invested`, `total_realized_pl`, `total_dividends`, `total_fees` should show as € with 2 decimals. Let me add these to the check:

```javascript
if (key === "average_cost" || key === "total_cost" || key === "total_realized_pl" ||
    key === "total_invested" || key === "total_dividends" || key === "total_fees") {
```

And for `total_trades` → plain integer. And `status` → string. This should work.

- [ ] **Step 4: Add renderAllocationChart function**

```javascript
function renderAllocationChart(products) {
  const ctx = document.getElementById("allocation-chart").getContext("2d");
  const openProducts = products.filter(p => p.status === "open" && p.total_invested > 0);
  const colors = ["#2563eb", "#16a34a", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16"];
  new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: openProducts.map(p => p.name),
      datasets: [{
        data: openProducts.map(p => p.total_invested),
        backgroundColor: openProducts.map((_, i) => colors[i % colors.length]),
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: "right" },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: €${ctx.parsed.toLocaleString()}`,
          },
        },
      },
    },
  });
}
```

- [ ] **Step 5: Add renderDividendChart function**

```javascript
function renderDividendChart(products) {
  const ctx = document.getElementById("dividend-chart").getContext("2d");
  const withDividends = products.filter(p => p.total_dividends > 0).sort((a, b) => b.total_dividends - a.total_dividends);
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: withDividends.map(p => p.name),
      datasets: [{
        label: "Dividends",
        data: withDividends.map(p => p.total_dividends),
        backgroundColor: "#2563eb",
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true } },
    },
  });
}
```

---

### Task 5: Verify everything works

- [ ] **Step 1: Start the Flask app**

```bash
cd C:\git\Pessoal\traderepublic && python app.py
```

- [ ] **Step 2: Open the browser at http://localhost:5000 and verify:**
   - Monthly P&L chart appears after summary cards
   - Product results table shows all products with correct data
   - Allocation doughnut chart shows open positions
   - Dividend bar chart shows products with dividends
   - All charts render without console errors

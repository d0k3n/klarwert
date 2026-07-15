# Dashboard Dark Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the dashboard visual presentation with a dark theme design system using pure CSS custom properties.

**Architecture:** Three file changes — full CSS rewrite with CSS variables (style.css), Chart.js color palette swap (dashboard.js), and minor HTML template updates (index.html). No new dependencies, no build step, no backend changes.

**Tech Stack:** Vanilla CSS (custom properties), Chart.js 4.4.4, Flask (no changes)

## Global Constraints

- Zero new npm/pip dependencies
- No changes to `app.py`, `portfolio/engine.py`, `portfolio/parser.py`
- All hex colors must come from the CSS custom properties defined in `:root`
- Numbers in `.num` columns must use monospace font
- All existing interactive behaviors (sort, group, filter) must remain unchanged

---

### Task 1: CSS Design System (`style.css`)

**Files:**
- Rewrite: `static/style.css` (all 33 lines)

**Interfaces:**
- Consumes: nothing (standalone CSS)
- Produces: CSS custom properties in `:root` consumed by `index.html` and `dashboard.js`

- [ ] **Step 1: Write the complete CSS rewrite**

The new `style.css` with full dark theme design system:

```css
:root {
  /* Background & Surface */
  --bg-primary: #0d1117;
  --bg-surface: #161b22;
  --bg-elevated: #21262d;
  --border-color: #30363d;
  --border-hover: #484f58;

  /* Text */
  --text-primary: #e6edf3;
  --text-secondary: #8b949e;
  --text-muted: #6e7681;

  /* Semantic */
  --color-positive: #3fb950;
  --color-negative: #f85149;
  --color-warning: #d29922;

  /* Accent */
  --accent-blue: #58a6ff;
  --accent-purple: #bc8cff;
  --accent-cyan: #79c0ff;
  --accent-orange: #ffa657;
  --accent-green: #7ee787;
  --accent-pink: #f778ba;

  /* Chart palette */
  --chart-1: #58a6ff;
  --chart-2: #3fb950;
  --chart-3: #d29922;
  --chart-4: #bc8cff;
  --chart-5: #ffa657;
  --chart-6: #79c0ff;
  --chart-7: #f778ba;
  --chart-8: #e6edf3;
}

* { box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  max-width: 1400px; margin: 0 auto; padding: 16px 24px;
  background: var(--bg-primary); color: var(--text-primary);
}

h1 {
  font-size: 1.3rem; font-weight: 700; margin: 0;
  font-family: 'SF Mono', 'JetBrains Mono', 'Cascadia Code', monospace;
}

h2 {
  font-size: 1.1rem; margin: 24px 0 8px; font-weight: 600;
  display: flex; align-items: center; gap: 8px;
}

h3 { font-size: 0.95rem; margin: 0 0 4px; font-weight: 600; color: var(--text-primary); }

/* Header */
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; margin-bottom: 20px;
  background: var(--bg-surface); border: 1px solid var(--border-color);
  border-radius: 8px;
}
.page-header .header-left { display: flex; align-items: center; gap: 12px; }
.page-header .header-subtitle { font-size: 0.8rem; color: var(--text-secondary); }
.page-header .header-right { display: flex; align-items: center; gap: 8px; }
.page-header .header-timestamp {
  font-size: 0.75rem; color: var(--text-muted);
  background: var(--bg-elevated); padding: 4px 10px; border-radius: 6px;
  border: 1px solid var(--border-color);
}
#reload-btn {
  background: transparent; color: var(--color-positive); border: 1px solid var(--color-positive);
  padding: 6px 14px; border-radius: 6px; font-size: 0.85rem; cursor: pointer;
  font-family: inherit; transition: all 0.15s;
}
#reload-btn:hover { background: #1f3a2e; }
#reload-status { font-size: 0.85rem; color: var(--text-secondary); margin-left: 8px; }

/* Summary Cards */
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px; margin-bottom: 16px;
}
.card {
  background: var(--bg-surface); border: 1px solid var(--border-color);
  border-radius: 8px; padding: 14px 16px; transition: border-color 0.15s;
}
.card:hover { border-color: var(--border-hover); }
.card .label {
  font-size: 0.7rem; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;
}
.card .value {
  font-size: 1.25rem; font-weight: 700; margin-top: 2px;
  font-family: 'SF Mono', 'JetBrains Mono', 'Cascadia Code', monospace;
}
.card .value.positive { color: var(--color-positive); }
.card .value.negative { color: var(--color-negative); }

#summary-by-asset-class .card .value {
  font-size: 0.85rem; font-weight: 600;
}
#summary-by-asset-class .card .label { margin-bottom: 6px; }

/* Section headers with badges */
.section-header {
  display: flex; align-items: center; gap: 8px; margin: 24px 0 8px;
}
.section-header h2 { margin: 0; }
.section-badge {
  background: var(--bg-elevated); color: var(--text-secondary);
  padding: 1px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 600;
}
.section-total {
  margin-left: auto; font-size: 0.8rem; color: var(--text-secondary);
}

/* Tables */
.table-wrapper {
  background: var(--bg-surface); border: 1px solid var(--border-color);
  border-radius: 8px; overflow: hidden; margin-bottom: 16px;
}
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 12px; text-align: left; }
th {
  background: var(--bg-primary); font-size: 0.7rem; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;
  cursor: pointer; user-select: none; border-bottom: 2px solid var(--bg-elevated);
}
th:hover { color: var(--text-primary); }
th.num, td.num { text-align: right; font-family: 'SF Mono', 'JetBrains Mono', 'Cascadia Code', monospace; }
td { border-bottom: 1px solid var(--bg-elevated); font-size: 0.85rem; }
tbody tr:hover { background: var(--bg-elevated); }
tbody tr:nth-child(even) { background: rgba(255,255,255,0.015); }
tbody tr:nth-child(even):hover { background: var(--bg-elevated); }

/* Asset class badges */
.asset-badge {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 0.75rem; font-weight: 500;
}
.asset-badge.stock { background: #1f3a2e; color: var(--color-positive); }
.asset-badge.derivative { background: #3d2e1a; color: var(--accent-orange); }
.asset-badge.fund { background: #1f2a3e; color: var(--accent-blue); }

/* Grouping controls */
.grouping-controls { margin-bottom: 8px; }
.group-dropdown {
  background: var(--bg-surface); color: var(--text-primary);
  border: 1px solid var(--border-color); border-radius: 6px;
  padding: 5px 10px; font-size: 0.85rem; cursor: pointer;
}
.group-row td { background: var(--bg-primary); font-weight: 600; border-bottom: 1px solid var(--border-color); }
.total-row td { font-weight: 700; border-top: 2px solid var(--text-secondary); background: var(--bg-elevated); }

/* Filter input */
#tx-filter {
  width: 100%; padding: 8px 12px; margin-bottom: 8px;
  background: var(--bg-surface); color: var(--text-primary);
  border: 1px solid var(--border-color); border-radius: 6px;
  font-size: 0.9rem; box-sizing: border-box;
}
#tx-filter::placeholder { color: var(--text-muted); }
#tx-filter:focus { outline: none; border-color: var(--accent-blue); }

/* Charts section */
#product-charts > div { display: flex; gap: 24px; flex-wrap: wrap; }
#product-charts > div > div { flex: 1; min-width: 300px; }

/* Responsive */
@media (max-width: 768px) {
  body { padding: 12px; }
  .page-header { flex-direction: column; gap: 8px; align-items: flex-start; }
  .cards { grid-template-columns: repeat(2, 1fr); }
  #product-charts > div > div { min-width: 100%; }
}
@media (max-width: 480px) {
  .cards { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: Save the file**

Write the above content to `static/style.css`.

---

### Task 2: HTML Template Updates (`index.html`)

**Files:**
- Modify: `templates/index.html`

**Interfaces:**
- Consumes: CSS class names from Task 1
- Produces: header structure section-header helpers

- [ ] **Step 1: Update the HTML template**

Replace `<h1>` and reload button with a `page-header` div, update `<h2>` tags to include section-header badges where applicable, wrap tables in `table-wrapper` divs.

Replace lines 11-14 (header area):
```html
<div class="page-header">
  <div class="header-left">
    <h1>Portfolio Analysis</h1>
    <span class="header-subtitle">TradeRepublic Dashboard</span>
  </div>
  <div class="header-right">
    <span class="header-timestamp">Last updated: <span id="header-timestamp"></span></span>
    <button id="reload-btn" onclick="window.reloadData()">&#x21bb; Reload Data</button>
    <span id="reload-status"></span>
  </div>
</div>
```

Replace each `<h2>` with a `div.section-header` wrapper (for sections with badges/totals). For sections without extra info (Card Expenses, Cash Flow, Product Charts, Monthly P&L), just keep `<h2>` as-is — the section data comes from JS.

Specifically:

For Open Positions, Closed Positions, Results by Product, Derivative Executions, and Recent Transactions — keep `<h2>` as-is (the grouping controls and badges are added dynamically by JS). But adding a `.section-header` wrapper is fine too.

Actually, looking at the current HTML, the simplest approach is:

1. Keep all `<h2>` as-is
2. Wrap each `<table>` (except transactions-table which has the filter input before it) in a `<div class="table-wrapper">`
3. Update the header
4. Update the `#tx-filter` (already has the right structure, CSS handles styling)

Let me be precise:

Replace lines 11-14:
```
<h1>Portfolio Analysis</h1>
<button id="reload-btn" onclick="window.reloadData()">&#x21bb; Reload CSV</button>
<div id="reload-status" style="display:inline-block; margin-left:12px; font-size:0.9em;"></div>
```
With:
```
<div class="page-header">
  <div class="header-left">
    <h1>Portfolio Analysis</h1>
    <span class="header-subtitle">TradeRepublic Dashboard</span>
  </div>
  <div class="header-right">
    <span class="header-timestamp" id="header-timestamp"></span>
    <button id="reload-btn" onclick="window.reloadData()">&#x21bb; Reload Data</button>
    <span id="reload-status"></span>
  </div>
</div>
```

Wrap tables in `<div class="table-wrapper">`:
- open-positions-table
- closed-positions-table
- product-results-table
- derivative-executions-table
- card-expenses-table

(transactions-table is handled differently since it has the filter input before it)

Remove `style` attributes (they're now in CSS):
- `#reload-status` inline style
- `#product-charts > div` inline style
- `#cash-flow-chart` height attribute (CSS or JS handles it)

- [ ] **Step 2: Remove inline styles from HTML**

Remove `style="display:inline-block; margin-left:12px; font-size:0.9em;"` from `#reload-status`.

Remove `style="display:flex; gap:24px; flex-wrap:wrap;"` from the product charts div (now in CSS).

Remove `height="250"` and `height="300"` from canvas elements (Chart.js `responsive: true` handles sizing).

- [ ] **Step 3: Save the file**

Write the updated content to `templates/index.html`.

---

### Task 3: Chart.js Color Palette (`dashboard.js`)

**Files:**
- Modify: `static/dashboard.js`

**Interfaces:**
- Consumes: chart color constants (self-contained in this file)
- Produces: charts with dark-theme-friendly colors

- [ ] **Step 1: Update color constants**

At the top of the file (after `const BASE = "";`), add the dark theme chart palette:

```js
const CHART_COLORS = [
  "#58a6ff", "#3fb950", "#d29922", "#bc8cff",
  "#ffa657", "#79c0ff", "#f778ba", "#e6edf3"
];
const CHART_GREEN = "#3fb950";
const CHART_RED = "#f85149";
const CHART_BLUE = "#58a6ff";
```

- [ ] **Step 2: Update `renderCashFlowChart`**

Change colors:
- `#16a34a` → `CHART_GREEN` (or `#7ee787`)
- `#dc2626` → `CHART_RED`
- `#2563eb` → `CHART_BLUE`
- Add chart options for dark theme (grid colors, tooltip styling)

New function (replace lines 375-394):
```js
function renderCashFlowChart(cf) {
  if (cashFlowChart) cashFlowChart.destroy();
  const ctx = document.getElementById("cash-flow-chart").getContext("2d");
  const labels = cf.map(d => d.month);
  cashFlowChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Deposits", data: cf.map(d => d.deposit), backgroundColor: "#7ee787" },
        { label: "Withdrawals", data: cf.map(d => d.withdrawal), backgroundColor: CHART_RED },
        { label: "Dividends", data: cf.map(d => d.dividend), backgroundColor: "#bc8cff" },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: "top", labels: { color: "#8b949e" } },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
      scales: {
        x: { stacked: false, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
        y: { beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
      },
    },
  });
}
```

- [ ] **Step 3: Update `renderMonthlyPLChart`**

Change `#16a34a` → `CHART_GREEN`, `#dc2626` → `CHART_RED`, add dark theme grid/tooltip options.

New function (replace lines 505-523):
```js
function renderMonthlyPLChart(data) {
  if (monthlyPLChart) monthlyPLChart.destroy();
  const ctx = document.getElementById("monthly-pl-chart").getContext("2d");
  monthlyPLChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map(d => d.month),
      datasets: [{
        label: "Realized P&L",
        data: data.map(d => d.realized_pl),
        backgroundColor: data.map(d => d.realized_pl >= 0 ? CHART_GREEN : CHART_RED),
      }],
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

- [ ] **Step 4: Update `renderAllocationChart`**

Replace `colors` array with `CHART_COLORS`, add dark theme options.

New function (replace lines 526-552):
```js
function renderAllocationChart(openPositions) {
  if (allocationChart) allocationChart.destroy();
  const ctx = document.getElementById("allocation-chart").getContext("2d");
  const open = openPositions.filter(p => p.total_cost > 0);
  allocationChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: open.map(p => p.name),
      datasets: [{
        data: open.map(p => p.total_cost),
        backgroundColor: open.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
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
}
```

- [ ] **Step 5: Update `renderDividendChart`**

Change `#2563eb` → `CHART_BLUE`, add dark theme options.

New function (replace lines 556-577):
```js
function renderDividendChart(products) {
  if (dividendChart) dividendChart.destroy();
  const ctx = document.getElementById("dividend-chart").getContext("2d");
  const withDividends = products.filter(p => p.total_dividends > 0).sort((a, b) => b.total_dividends - a.total_dividends);
  const barColors = withDividends.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);
  dividendChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: withDividends.map(p => p.name),
      datasets: [{
        label: "Dividends",
        data: withDividends.map(p => p.total_dividends),
        backgroundColor: barColors,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
      scales: {
        x: { beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
        y: { ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
      },
    },
  });
}
```

- [ ] **Step 6: Save the file**

Write the updated content to `static/dashboard.js`.

---

### Task 4: Verification

- [ ] **Step 1: Start the Flask server and verify the dashboard loads**

```bash
cd /c/git/Pessoal/traderepublic
python -m flask run
```

Expected: Server starts on http://localhost:5000.

- [ ] **Step 2: Open http://localhost:5000 in browser**

- [ ] **Step 3: Verify visually:**
  - Dark background (#0d1117) is applied
  - Summary cards are visible with correct colors
  - Tables have dark theme styling
  - Charts render with new color palette
  - Sort, group, and filter still work
  - Reload button works
  - Page is responsive when resizing

- [ ] **Step 4: Check browser console for errors**

Expected: No JavaScript errors.

- [ ] **Step 5: Commit**

```bash
git add static/style.css static/dashboard.js templates/index.html
git commit -m "feat: dark theme dashboard redesign"
```

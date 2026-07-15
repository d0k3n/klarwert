# Product Charts & Results — Design Spec

## Overview
Add per-product aggregated results and monthly realized P&L chart to the Trade Republic portfolio dashboard.

## Backend Changes

### `engine.py`
Extend `run_engine()` to compute two new outputs:

1. **Products** (`per_product`): dict keyed by ISIN with:
   - `isin`, `name`, `asset_class`
   - `status`: "open" | "closed" | "both"
   - `total_invested`: cost basis of buys (open positions only)
   - `total_realized_pl`: sum of realized P&L from closed lots
   - `total_dividends`: sum of dividends for this ISIN
   - `total_fees`: sum of fees for trades in this ISIN
   - `total_trades`: count of BUY+SELL transactions

   Aggregate by grouping trades per ISIN. Collect dividends from `cash_rows` where `symbol` matches the ISIN.

2. **Monthly P&L** (`monthly_pl`): list of `{month: "YYYY-MM", realized_pl: float}`.
   During lot matching, record the realized P&L per SELL transaction with its month, then aggregate.

### `app.py`
Add two new API routes:

- `GET /api/products` → `jsonify(compute_data(...)["products"])`
- `GET /api/monthly_pl` → `jsonify(compute_data(...)["monthly_pl"])`

Both respect the knocked-down flagging (filter out knocked BUYs before computation).

## Frontend Changes

### `templates/index.html`
Add new sections after closed positions table (before cash flow chart):

1. `<section id="product-results">` — product results table
2. `<section id="product-charts">` — side-by-side allocation and dividend charts

Move monthly P&L chart before open positions table.

### `static/dashboard.js`
Fetch new API endpoints and render:

1. **Monthly P&L Bar Chart**: Chart.js bar chart, bars colored green (`#16a34a`) for positive and red (`#dc2626`) for negative. Rendered before open positions.

2. **Allocation Doughnut Chart**: Chart.js doughnut chart showing total_invested per product (open positions only). Different colors per slice. Rendered in the product-charts section.

3. **Dividends Horizontal Bar Chart**: Chart.js bar chart, horizontal, showing dividends per product. Rendered next to allocation chart.

4. **Product Results Table**: Sortable table with columns:
   - Name, ISIN, Asset Class, Status, Invested (€), Realized P&L (€), Dividends (€), Fees (€), Trades
   - P&L positive → green, negative → red

### `static/style.css`
Minor additions if needed for new table styling.

## Data Flow
1. User loads page
2. `dashboard.js` fetches all 8 endpoints in parallel (6 existing + 2 new)
3. Renders summary cards → monthly P&L chart → open positions → closed positions → product table → product charts (allocation + dividends) → cash flow chart → transactions

## Implementation Order
1. Extend `engine.py` — compute `per_product` and `monthly_pl`
2. Add API routes in `app.py`
3. Update `index.html` with new sections
4. Implement rendering in `dashboard.js`
5. Verify all data loads and charts render correctly

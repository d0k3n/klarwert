# Portfolio Analysis Dashboard — Design Spec

## 1. Purpose & Scope

Build a local, lightweight web dashboard that reads the Trade Republic export `transactions.csv` and presents:

- **Open positions** shown at cost basis (average purchase price, no live market data).
- **Closed positions** with realized profit/loss calculated using FIFO matching per ISIN.
- **Cash-flow summary** covering deposits, withdrawals, dividends, interest, fees, and card transactions.
- **Trading activity** including recent buys, sells, and dividends.

No external market-data APIs are used. All values are derived from the provided CSV.

## 2. Context

The repository currently contains a single file, `transactions.csv`, exported from Trade Republic. The file includes cash, card, transfer, interest, dividend, and trading rows for stocks, funds, and derivatives.

## 3. Architecture

```
transactions.csv
      │
      ▼
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│   parser    │────▶│ portfolio engine│────▶│  Flask API  │
│  (pandas)   │     │   (FIFO logic)  │     │   (app.py)  │
└─────────────┘     └─────────────────┘     └──────┬──────┘
                                                   │
                                                   ▼
                                          ┌─────────────────┐
                                          │  HTML + vanilla │
                                          │      JS         │
                                          │  (dashboard)    │
                                          └─────────────────┘
```

- **Backend**: Flask serves JSON endpoints; pandas performs data processing.
- **Frontend**: Single-page HTML dashboard using vanilla JavaScript and Chart.js (loaded from CDN).
- **Data loading**: `transactions.csv` is parsed once at server startup and kept in memory.

## 4. Components & File Structure

```
traderepublic/
├── transactions.csv              # source data (already present)
├── app.py                        # Flask application and API routes
├── requirements.txt              # Python dependencies
├── portfolio/
│   ├── __init__.py
│   ├── parser.py                 # CSV loading and normalization
│   └── engine.py                 # FIFO matching, P&L, aggregations
├── templates/
│   └── index.html                # dashboard markup
├── static/
│   ├── dashboard.js              # fetch data and render UI
│   └── style.css                 # basic styling
└── tests/
    ├── test_parser.py
    └── test_engine.py
```

### Responsibilities

- **`parser.py`**: Reads `transactions.csv`, normalizes dates and numeric columns, and classifies rows into transaction types (`BUY`, `SELL`, `DIVIDEND`, `INTEREST`, `TRANSFER`, `CARD`, etc.).
- **`engine.py`**: Groups trades by ISIN, applies FIFO lot matching for sells, computes realized P&L, tracks remaining open lots, and aggregates cash-flow items.
- **`app.py`**: Exposes computed data as JSON endpoints and serves `index.html` at `/`.
- **`dashboard.js`**: Calls the API and renders summary cards, tables, and charts.

## 5. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves `templates/index.html` |
| `GET` | `/api/summary` | Aggregated totals: deposits, withdrawals, dividends, interest, fees, realized P&L, current invested amount |
| `GET` | `/api/open_positions` | Open holdings: ISIN, name, asset class, shares, average cost, total cost |
| `GET` | `/api/closed_positions` | Realized performance per ISIN: name, total realized P&L, number of closed lots, shares sold |
| `GET` | `/api/cash_flow` | Monthly aggregates of deposits, withdrawals, dividends, fees |
| `GET` | `/api/transactions` | Filterable list of trading transactions (buy/sell/dividend) |

## 6. FIFO Logic

For each ISIN with trading activity:

1. Collect all `BUY` rows as purchase lots ordered by datetime.
2. For each `SELL`, consume the oldest open lot first until the sold quantity is fully matched.
3. Realized P&L for the sell = Σ (sell proceeds attributed to lot − cost basis of that lot).
4. Remaining unmatched lots form the **open position**.
5. Average cost of the open position = remaining cost basis / remaining shares.

Cash-flow items (transfers, dividends, interest, fees, card transactions) are categorized from the existing `type` and `category` columns and aggregated separately.

## 7. Dashboard UI Layout

Top-to-bottom sections on a single page:

1. **Summary cards** — total invested, realized P&L, dividends, interest, fees, net cash deposited.
2. **Open positions table** — sortable; columns: ISIN, name, asset class, shares, average cost, total cost.
3. **Closed positions table** — ISIN, name, total realized P&L, closed lots, total shares sold.
4. **Cash-flow chart** — monthly bar chart of deposits, withdrawals, and dividends.
5. **Recent transactions** — last 50 trading transactions with search/filter by symbol or name.

Styling is intentionally minimal; Chart.js is loaded from CDN.

## 8. Error Handling

- Missing or unreadable `transactions.csv` causes the server to exit with a clear error before starting.
- Rows with unparseable numeric fields are skipped with a logged warning.
- Sells that exceed the total bought quantity log a warning and are treated as a short sale (negative open position).
- Non-trading rows are ignored by the FIFO engine but included in cash-flow aggregations.

## 9. Testing

- `tests/test_parser.py`: Verify CSV loading, date/numeric parsing, and transaction-type classification.
- `tests/test_engine.py`: Verify FIFO lot matching with synthetic datasets including partial sells, multiple lots, and same-ISIN round trips.

## 10. Dependencies

- `flask`
- `pandas`

Front-end dependencies are loaded via CDN (Chart.js).

## 11. Open Questions / Future Extensions

- Live market prices could be added later as an optional module.
- Benchmark comparison or time-weighted returns could be added once historical prices are available.
- CSV reload endpoint could be added for updates without restarting the server.

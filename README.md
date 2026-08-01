# Klarwert

**Klarwert** (German: "clear value") is a local-first portfolio analyzer for Trade Republic CSV exports. Drop in your broker export and get an audit trail, a per-year tax report, performance metrics, unrealized P&L, income and spending analytics, and position concentration.

All computation happens on your machine. Your data never leaves it.

---

## Features

- **Summary cards** - XIRR (annualized), win rate on closed positions, average win/loss, estimated market value and unrealized P&L, top-5 concentration.
- **Reconciliation** - sources vs uses of cash, including trade fees and taxes.
- **Monthly Realized P&L** - realized profit/loss per month.
- **Open & Closed Positions** - cost basis, current market value, unrealized P&L, position weights.
- **Results by Product** - dividends (gross / WHT / net), realized P&L, yield on cost.
- **Derivative Executions** - warrant and knock-out (TILG) exercises, including knocked down lots.
- **Product Charts** - allocation by product and dividends.
- **Income View** - stacked monthly income chart and full dividend history.
- **Cash Flow** - deposits, withdrawals and balances over time.
- **Card Spending** - doughnut by MCC category plus a monthly bar chart.
- **FIFO Audit Trail** - per-lot sale matches (buy date, cost basis, proceeds, P&L).
- **Tax Report** - per-fiscal-year disposals with CSV export.
- **Recent Transactions** - full searchable/groupable transaction table.

## Requirements

- Python 3.11+
- All other dependencies install automatically (see below).

Live price auto-fetch is optional and uses Finnhub's free tier. To enable it,
create a `.env` file in the project root with your free API key:

```
FINNHUB_API_KEY=your_key_here
```

Get a key at https://finnhub.io/register. Without it, the price-refresh button is
disabled and manual price entry is still available. All computation stays local.

## Setup

```bash
git clone git@github.com:YOUR_USER/klarwert.git
cd klarwert
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

### Browser (recommended for daily use)

```bash
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

### Desktop app (PyWebView window)

```bash
python desktop_app.py
```

### Build a standalone executable (PyInstaller)

```bash
python build.py
```

The built binary lands in `dist/` as `Klarwert` (your current `build`/`dist` folders are git-ignored).

## Loading your data

1. In the Trade Republic app/web, export your transactions as a CSV file.
2. Two ways to load it:
   - **Drop-in file** - save the export as `transactions.csv` in the project folder (or in the data folder shown at startup on Windows), then start the app or click **Reload Data**.
   - **In-app upload** - click **Load CSV** and pick the file. (Recommended for the browser version.)
3. Once loaded you can optionally set **manual market prices** per ISIN to see current market value and unrealized P&L (stored locally in `prices.json`).

Optional files read alongside `transactions.csv`:

- `knocked_down.json` - manually flag transactions whose knock-out was lost (Knocked? column).
- `prices.json` - manual market prices, written by the app when you enter them in the UI.

## Notes

- Facts about your broker are described only as a **data source**; "Klarwert" is an independent, unofficial tool not affiliated with or endorsed by Trade Republic.
- Everything stays on your machine - no telemetry, no uploads.

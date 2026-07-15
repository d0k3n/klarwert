# Knocked-Down Flag for Open Positions

## Problem
Derivatives (turbos, warrants) that expire worthless remain in the open positions list with no sell transaction to remove them. The user needs a way to manually flag specific **buy transactions** as "knocked down" (expired) so that:
- Dead lots are excluded from position calculations
- The remaining position reflects only live holdings

## Design

### What Gets Flagged
Individual **buy transactions** (by `transaction_id`) are flagged, not whole ISINs. A position may have 10 buys — flagging one removes only that lot from the computation.

### Backend: Flag Persistence
- Store knocked-down transaction IDs in `knocked_down.json` alongside `transactions.csv`
- Two API endpoints:
  - `GET /api/knocked_down` → `{ "ids": ["txn-id-1", "txn-id-2", ...] }`
  - `POST /api/knocked_down/toggle` → body `{ "id": "..." }` toggles the flag

### API Layer
- `knocked_down.json` is read on every `/api/open_positions` request
- Flagged BUY rows are **filtered out** of the DataFrame before passing to `run_engine()`
- This means the engine code stays pure — no changes to `portfolio/engine.py`
- `GET /api/knocked_down` is still available for the frontend to pre-mark checkboxes

### Frontend
- In the **Transactions table**, add a "Knocked?" column with a checkbox
- Only BUY transactions get a clickable checkbox (non-BUY rows show `—`)
- On page load, fetch `/api/knocked_down` and check the matching boxes
- Clicking toggles via `POST /api/knocked_down/toggle` and updates the UI
- The **Open Positions** table automatically reflects the change on next reload/refresh

### Styling
- Knocked-down transactions get a muted/strikethrough row style
- The check mark column is narrow

### Files Changed
1. `knocked_down.json` (new) — persistent store
2. `app.py` — add two new routes, filter flagged buys before engine
3. `static/dashboard.js` — fetch flags, render checkbox column, handle clicks
4. `templates/index.html` — add "Knocked?" column header to transactions table
5. `static/style.css` — knocked-row styling

### Non-Goals
- No changes to `portfolio/engine.py`
- No auto-detection
- No authentication

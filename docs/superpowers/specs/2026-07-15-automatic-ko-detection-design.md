# Automatic KO Detection (Auto-Knocked)

## Problem

Derivative purchases (turbos, warrants) that are knocked out remain in the open positions list because there is no explicit sell transaction to close them. Currently, each KO must be manually flagged via the UI checkbox, which is error-prone — the user forgets to flag, and dead lots pollute the portfolio view.

## Solution

Automatically detect KO'd derivative BUY transactions by matching unsold BUY lots against TR-generated **WARRANT_EXERCISE** rows.

### How KO Detection Works

TR generates two rows when a derivative is knocked out:
- **WARRANT_EXERCISE**: records the quantity exercised (matches the KO'd BUY quantity)
- **TILG**: records any residual cash return (usually small, e.g. €1.00)

The auto-detection logic (`auto_detect_knocked` in `portfolio/engine.py`):

1. Filters all derivative ISINs from the DataFrame
2. For each ISIN, runs FIFO matching on BUY/SELL pairs to determine which lots were sold
3. Identifies **remaining BUY lots** (not consumed by any SELL)
4. Sums remaining shares and compares to total WARRANT_EXERCISE shares for that ISIN
5. If they match within 0.01 tolerance, all remaining BUY lots are confirmed KO'd
6. Returns the set of `transaction_id` values for those KO'd lots

### Edge Cases Covered

| Pattern | Example Data | Detection |
|---------|-------------|-----------|
| **Total KO** — no sells, all BUY'd shares knocked out | DE000FA6ZNB7: BUY 1352, WE 1352 | All BUY lots auto-flagged |
| **Hybrid KO** — some lots sold, remainder knocked out | DE000FD8KV76: BUY 3661, SELL 1161, WE 2500 | Remaining 3 lots (1000+1000+500) auto-flagged |
| **No KO** — derivative still open, no WE rows | DE000FD8QEA0: BUY 1800, SELL 500, no WE | Not flagged — remains open |
| **No KO** — all lots sold normally | DE000FA64RA4: BUY 100, SELL 100, no WE | Not flagged — closed normally |

### Files Changed

#### `portfolio/engine.py`

- Add `auto_detect_knocked(df)` function
- Signature: `auto_detect_knocked(df: pd.DataFrame) -> set[str]`
- Returns set of auto-detected KO'd transaction IDs
- Uses existing `Lot` dataclass and FIFO logic (reuses same patterns)

#### `app.py`

- Modify `compute_data(flagged_ids)` → `compute_data(manual_ids, auto_ids)`
- Calls `auto_detect_knocked()` on the full DataFrame
- Merges auto-detected IDs with manual flags before calling `run_engine()`
- The merged set is also passed to `compute_derivative_executions()`

#### No frontend changes

- Auto-detected KO's are transparent to the UI — they appear as knocked=true in the data, and the Transactions table checkbox will reflect their status
- The manual toggle still works for overrides

### Data Flow

```
auto_detect_knocked(df) ──┐
                           ├── merge IDs ──▶ run_engine(df with knocked=True)
knocked_down.json ────────┘                          │
                                                     ▼
                                          compute_derivative_executions(merged_ids)
```

### Non-Goals

- No new API endpoints
- No frontend changes
- No changes to `knocked_down.json` schema
- No changes to `run_engine()` core logic
- No changes to `parser.py`

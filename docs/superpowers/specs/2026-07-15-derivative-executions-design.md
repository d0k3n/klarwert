# Derivative Executions — Design Spec

## Motivation

Derivative products (warrants, knock-outs) have a lifecycle where a BUY position
can be knocked out (KO), followed by a WARRANT_EXERCISE and a TILG cash return.
Currently the KO loss is recorded but the warrant return (TILG) is not
accounted for, giving an incomplete picture of the actual P&L.

## Data Model

For each derivative ISIN, group the following transactions:

| Field | Source | Description |
|---|---|---|
| `name` | Any DERIVATIVE row | Product name |
| `isin` | — | ISIN identifier |
| `ko_quantity` | BUY rows flagged as KO | Sum of shares from KO'd lots |
| `ko_loss` | BUY rows flagged as KO | Sum of (shares × price), negative |
| `ko_fees` | BUY rows flagged as KO | Sum of fees, negative |
| `ko_total` | — | `ko_loss + ko_fees` |
| `warrant_quantity` | WARRANT_EXERCISE rows | Sum of |shares| from warrant exercises |
| `warrant_return` | TILG rows (description contains "Warrant Exercise") | Sum of amount, positive |
| `net_result` | — | `ko_total + warrant_return` |
| `reconciled` | — | `ko_quantity == warrant_quantity` |

## API

**`GET /api/derivative_executions`** returns:

```json
{
  "executions": [
    {
      "name": "Long 75,02 $",
      "isin": "DE000FE37UZ3",
      "asset_class": "DERIVATIVE",
      "ko_quantity": 269,
      "ko_loss": -1001.49,
      "ko_fees": -1.00,
      "ko_total": -1002.49,
      "warrant_quantity": 269,
      "warrant_return": 704.78,
      "net_result": -297.71,
      "reconciled": true
    }
  ]
}
```

## Frontend

New `<section id="derivative-executions">` in `index.html` after the product
results table. Table columns:

| Name | ISIN | KO'd Qty | KO Loss | Warrant Return | Net Result | Reconciled? |
|---|---|---|---|---|---|---|

New `renderDerivativeExecutions(data)` function in `dashboard.js`, called from
`loadAllData()`.

Only products with `asset_class == "DERIVATIVE"` and at least one KO'd BUY or
WARRANT_EXERCISE are shown.

## Files Changed

- `portfolio/engine.py` — add `compute_derivative_executions(df, knocked_ids)`
- `app.py` — add `/api/derivative_executions` endpoint
- `templates/index.html` — add new section with table
- `static/dashboard.js` — add render function, call from `loadAllData()`

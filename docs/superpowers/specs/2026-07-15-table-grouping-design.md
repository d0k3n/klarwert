# Table Grouping Design

## Goal

Make all tables in the Trade Republic dashboard groupable by user-selected columns, with automatic summation of numeric values and a total row.

## Approach

**Pure frontend grouping** — all data is already fetched client-side. No backend changes needed. Grouping is instant with zero API calls.

## Per-Table Configuration

| Table ID | Groupable By | Summable Columns | Special Notes |
|---|---|---|---|
| product-results-table | asset_class, status | total_invested, total_realized_pl, total_dividends, total_fees, total_trades | — |
| open-positions-table | asset_class | shares, total_cost | average_cost recalculated = total_cost / shares |
| closed-positions-table | asset_class | total_realized_pl, closed_lots, total_shares_sold | — |
| derivative-executions-table | asset_class, reconciled | ko_quantity, ko_loss, ko_fees, ko_total, warrant_quantity, warrant_return, net_result | — |
| transactions-table | type, asset_class | shares, amount | — |
| card-expenses-table | name (merchant) | amount | — |

## UI

1. **Dropdown selector** — A `<select>` element inserted above each table's `<thead>`. Options: "None" (default, shows individual rows) + each groupable column (display labels like "Asset Class", "Status", etc.)
2. **Grouped rows** — Each group value becomes one aggregate row. The group label cell is styled bold/emphasized.
3. **Total row** — A fixed row at the bottom of `<tbody>` (or a `<tfoot>`) showing "Total" in the group column and summed values in all numeric columns.

## Implementation

### `makeTableGroupable(tableId, config)` utility function

- Reads the table's existing column structure (`<th>` elements with `data-sort` and `data-field` or matching keys)
- Creates and inserts a `<select>` dropdown before the table
- On dropdown change: re-renders the table in grouped or ungrouped mode
- Keeps existing sort-on-click behavior working in both modes

### Config object shape

```js
{
  groupColumns: ['asset_class', 'status'],           // field keys
  groupLabels: { asset_class: 'Asset Class', ... },  // display labels
  numericFields: ['total_invested', 'total_fees'],   // fields to sum
  averageFields: ['average_cost'],                    // fields to recalculate
  render: function(data) { ... }                      // original render function
}
```

### Grouping logic

```
function groupData(data, groupBy, numericFields, averageFields)
  → [{ groupKey, groupLabel, sums: {...}, averages: {...} }, ...]
  + totals row
```

### Integration per table

- Product Results, Open Positions, Closed Positions — wrap `renderTable()`: when grouped, render aggregate rows instead of individual rows
- Transactions — wrap `renderTransactions()`: same pattern
- Derivative Executions — wrap `renderDerivativeExecutions()`: same pattern
- Card Expenses — wrap `renderCardTransactions()`: same pattern

## Edge Cases

- **Single-item groups**: Still show as a group row (consistent layout)
- **All rows have same group value**: Single group row + total row
- **No numeric data in a group**: Show 0 or "—" for summed columns
- **Dropdown on "None"**: Show original individual rows, no total row
- **Empty data**: Dropdown still shown but table body is empty
- **Sort + Group combined**: Clicking a column header sorts the aggregate rows by that column's sum value

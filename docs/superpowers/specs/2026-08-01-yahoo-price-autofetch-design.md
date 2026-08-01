# Yahoo Price Auto-Fetch — Design Spec

## Motivation

Market value and unrealized P&L for open positions currently require the user to
type the current price per ISIN by hand into `prices.json` via the UI. This is
tedious and goes stale. We can auto-fetch current prices from a free, keyless
source (Yahoo Finance) so the user can refresh all open positions with one
click, while still allowing manual entry as an override.

## Free price source: Yahoo Finance

Two keyless JSON endpoints (no API key):

1. `https://query1.finance.yahoo.com/v1/finance/search?q=<isin>`
   Resolve an ISIN to the exact ticker Yahoo quotes prices under. Yahoo quotes by
   ticker, not ISIN, so this lookup is the ISIN → ticker bridge.
2. `https://query1.finance.yahoo.com/v1/finance/chart/<ticker>`
   Returns `chart.result[0].meta.regularMarketPrice` (native price) and
   `meta.currency` (the instrument's native currency code).

Because positions are keyed by ISIN, every refresh needs the search → chart flow.

## Data model: prices.json

Extend the stored shape so we know whether a price was entered manually or
auto-fetched (manual must override auto).

New shape — `{isin: {"price": float, "source": "manual"|"yahoo"}}`.

Backwards-compatible: an existing flat `{isin: float}` entry (from before this
change) is loaded as `{isin: {"price": x, "source": "manual"}}`.

`source == "manual"` is sticky: a refresh never overwrites it. `source ==
"yahoo"` (or a flat legacy number) may be overwritten by the next refresh.

## Ticker cache: tickers.json

Resolving ISIN → ticker costs one HTTP round-trip per ISIN on every refresh.
Cache the mapping in `tickers.json` (`{isin: ticker}`) so repeat refreshes don't
need the network. The cache is refreshed implicitly only when a position's ISIN
is not present (rare) or clears on a failed match.

## New module: portfolio/market.py

Focused, separately-testable unit. Pure functions of network + inputs.

- `resolve_ticker(isin, session) -> str | None` — query search endpoint, pick the
  best quote. Prefer `quoteType` in `{EQUITY, ETF, CRYPTOCURRENCY}`; reject
  `DERIVATIVE`-type and obviously wrong matches. Return the symbol or None.
- `fetch_price(ticker, session) -> (float, str) | None` — query chart endpoint,
  return `(regularMarketPrice, currency)`.
- `eur_rate(session) -> float` — query `chart/EUR=X`, return the EUR/USD rate
  (cached in-memory per refresh).
- `to_eur(amount, currency, session) -> float` — if currency == `EUR` return as
  is, else multiply by `eur_rate()`.
- `refresh_prices(positions, existing_prices, ticker_cache, session) -> dict`
  — for each open position: skip when existing source is `manual`; else resolve
  ticker, fetch native price, convert to EUR. Return `{prices, tickers, skipped}`
  where:
  - `prices` — `{isin: {"price": eur_float, "source": "yahoo"}}` for successfully
    updated positions,
  - `tickers` — `{isin: ticker}` for resolved positions (to persist the cache),
  - `skipped` — list of `{isin, reason}` for unrecognized positions (not an
    error; manual entry remains possible).

HTTP via `requests` (new dependency). Network failures are caught per-ISIN and
surfaced as `skipped` / logged, never raised to fail the whole refresh.

## API additions (app.py)

- `GET /api/tickers` — return the persisted ticker cache (so the UI can show
  resolved symbols).
- `POST /api/refresh_prices` — run `refresh_prices` over current open positions;
  merge results into `prices.json` (respecting manual sticky) and persist the
  ticker cache to `tickers.json`. Return `{prices, skipped}`.

No change to `GET /api/prices` shape at the flat level beyond the new entries;
backwards-compatible.

## apply_prices (engine.py)

Unchanged externally. It must read the price values from the new nested shape
(tolerate both flat legacy numbers and new objects). Downstream market-value and
unrealized-P&L math is untouched.

## Frontend (dashboard.js + index.html)

- Add a **"Refresh prices (Yahoo)"** button beside the price-inputs section.
- On click: `POST /api/refresh_prices`, then reload all data; show a short status
  line ("Updated 3 prices; skipped 2"). While running, disable the button.
- Existing manual price inputs keep their behavior but now POST with
  `source: "manual"`.
- If there are no open positions, the button is hidden/disabled.

## Error handling & resilience

- No network → manual entry still fully works; button shows a failure status.
- Per-ISIN failures are isolated (skipped), never block the batch.
- Unknown/missing ISINs and derivatives that Yahoo can't resolve are skipped,
  with reasons shown in the status line.

## Testing

- Unit tests for `portfolio/market.py` with Yahoo endpoints mocked (requests
  responses injected via the `session` parameter):
  - resolve_ticker picks the right quote and rejects derivatives;
  - fetch_price returns price + currency;
  - to_eur converts USD and leaves EUR alone;
  - refresh_prices does NOT overwrite `manual`-stamped prices;
  - refresh_prices converts a USD position to EUR.
- A test that `apply_prices` still works with both flat and nested price shapes.

## Dependency

- Add `requests>=2.0` to `requirements.txt`.

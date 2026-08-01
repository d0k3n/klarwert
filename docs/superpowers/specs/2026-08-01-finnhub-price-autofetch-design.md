# Finnhub Price Auto-Fetch — Design Spec

## Motivation

The Yahoo Finance auto-fetch introduced earlier (see
`2026-08-01-yahoo-price-autofetch-design.md`) is broken in practice: Yahoo's
`query1/query2.finance.yahoo.com` endpoints return HTTP 429 (rate-limited/blocked)
for server-side requests without a browser session, so `refresh_prices` resolves
no ISINs and fetches no prices. Stooq (the keyless fallback candidate) now serves
an anti-bot JS challenge to non-browser clients, so it is not viable either.

This spec swaps the price source from Yahoo Finance to **Finnhub**, a real-time
market data API with a free tier (60 requests/minute) that works server-side with
a plain API key.

## Requirements

- Price auto-fetch must work again (resolve ISIN → ticker, fetch live price,
  convert to EUR) using **Finnhub**.
- **No key configured → the feature is unavailable**: the refresh endpoint
  returns a disabled state and the UI hides/grays the refresh button. Manual
  price entry continues to work with no key.
- The API key is read from the `FINNHUB_API_KEY` environment variable, with a
  fallback to a gitignored `.env` file in the project root. No key in source.
- Manual prices remain sticky overrides (existing behavior, unchanged).

## Free price source: Finnhub

Three endpoints replace the Yahoo ones:

1. `GET https://finnhub.io/api/v1/search?q=<isin>&token=<key>`
   Resolve an ISIN to a ticker. Response: `{"result": [{"symbol": "...",
   "displaySymbol": "...", "type": "Common Stock"|"ETP"|...}]}`. Verified to
   resolve real Trade Republic ISINs (e.g. `IE00B5BMR087` → `CSPX.L`,
   `DK0062498333` → `NOVO B.CO`, `NL0010273215` → `ASML.AS`).
2. `GET https://finnhub.io/api/v1/quote?symbol=<ticker>&token=<key>`
   Live quote. Response `{"c": <current price>, ...}`. `c` is the instrument's
   native-currency price.
3. `GET https://finnhub.io/api/v1/stock/profile2?symbol=<ticker>&token=<key>`
   Company/ETF profile. Response includes `"currency"` (native currency code).
   **Free-tier limitation**: blocked (`"You don't have access to this
   resource."`) for many London-listed ETPs and some symbols, so it is a
   best-effort lookup, not a required one.

### Currency determination

Finnhub's `quote` does not return a currency. The native currency is resolved in
priority order:

1. `profile2.currency` when it succeeds;
2. inferred from the ticker suffix when profile2 is blocked:
   - `.L` → `GBP`, `.DE`/`.F`/`.BE`/`.PA`/`.AS`/`.MI` → `EUR`,
     `.CO` → `DKK`, `.T` → `JPY`, `.TO` → `CAD`, no suffix → `USD`;
3. default `EUR` when nothing else yields a currency.

### FX conversion (improvement over Yahoo path)

The old Yahoo path only fetched USD→EUR and mishandled other currencies.
Frankfurter (`api.frankfurter.dev`) supports **any** base currency
(`?base=GBP&symbols=EUR`), so the module now exposes
`fx_rate(currency, session) -> float` which converts any of the instrument
currencies above to EUR, cached in-memory per refresh. `to_eur` becomes a thin
wrapper: `EUR` → identity, else `amount * fx_rate(currency)`.

## Data model

Unchanged from the Yahoo spec: `prices.json` is
`{isin: {"price": float, "source": "manual"|"auto"}}` (backwards-compatible with
flat legacy numbers, loaded as `manual`), and `tickers.json` caches
`{isin: ticker}`.

`source == "manual"` is sticky and never overwritten. Auto-fetched prices are
stamped `"auto"` (renamed from the old `"yahoo"` value; legacy `"yahoo"` values
are treated as auto/overwritable on load).

## portfolio/market.py (rewrite of the Yahoo client)

Focused, separately-testable module. Pure functions of network + inputs.

- `_config()` — load `FINNHUB_API_KEY` from env, else from a gitignored `.env`
  file (simple `KEY=VALUE` lines) in the project root. Exposes
  `is_configured() -> bool`.
- `resolve_ticker(isin, session) -> str | None` — Finnhub `search?q=<isin>`,
  pick the first result whose `type` is in a good set
  (`Common Stock`, `ETP`, `ADR`, `Fund`, ...); reject `DERIVATIVE`-type and
  obviously wrong matches. Return symbol or `None`.
- `fetch_price(ticker, session) -> (float, str) | None` — Finnhub
  `quote?symbol=<ticker>` → `(c, currency)` where currency comes from
  `profile2` or suffix inference.
- `fx_rate(currency, session) -> float` — Frankfurter
  `latest?base=<currency>&symbols=EUR`; cached in-memory per refresh.
- `to_eur(amount, currency, session) -> float` — identity for EUR, else multiply
  by `fx_rate(currency)`.
- `refresh_prices(positions, existing_prices, ticker_cache, session) -> dict`
  — same contract as before (`{prices, tickers, skipped}`), but:
  - raises/immediately returns `{"disabled": True}` when no key is configured
    (caller decides how to surface it);
  - quotes are rate-limited with a small delay (free tier: 60 req/min).

Network failures are caught per-ISIN and surfaced as `skipped`, never raised to
fail the whole refresh. HTTP via existing `requests` dependency.

## API changes (app.py)

- `POST /api/refresh_prices` — when no key is configured, return
  `{"enabled": False, "reason": "no_api_key"}` with the UI showing a
  "no key configured" state instead of an error. When configured, run
  `refresh_prices`, merge into `prices.json` (respecting manual sticky), persist
  `tickers.json`, return `{prices, skipped}` as before.
- `GET /api/refresh_status` (new, optional) — returns `{"enabled": bool}` so the
  UI can render the button state on load without POSTing.

## Frontend (dashboard.js + index.html)

- The "Refresh prices" button is hidden/grayed when the API reports
  `enabled: false` (no key). Tooltip/label: "No Finnhub API key configured".
- No other UI change; manual price inputs keep their behavior.

## Error handling & resilience

- No key → feature off, manual entry still fully works.
- No network → manual entry still fully works; button shows a failure status.
- Per-ISIN failures are isolated (skipped), never block the batch.
- Unknown/missing ISINs and German warrants/knockouts that Finnhub can't resolve
  are skipped, with reasons shown in the status line (same as Yahoo behavior).

## Configuration

- `.env` in project root, gitignored, containing `FINNHUB_API_KEY=<key>`.
- `.gitignore`: add `.env`.
- README: document the optional key setup and that without it the live-price
  feature is disabled.

## Testing

- Rewrite `tests/test_market.py` to mock the Finnhub endpoints (search, quote,
  profile2) and Frankfurter, via the injected `session` parameter:
  - resolve_ticker picks the right result and rejects derivatives;
  - fetch_price returns price + currency (profile2 and suffix paths);
  - fx_rate/to_eur convert GBP/DKK/JPY/USD and leave EUR alone;
  - refresh_prices does NOT overwrite `manual`-stamped prices;
  - refresh_prices converts a non-EUR position to EUR;
  - refresh_prices is disabled (no key) when no key is configured.
- A test that `apply_prices` still works with both flat and nested price shapes
  (unchanged, but kept green).

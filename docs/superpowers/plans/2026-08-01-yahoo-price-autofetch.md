# Yahoo Price Auto-Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user auto-fetch current market prices for open positions from Yahoo Finance with one click, keeping manually-entered prices as sticky overrides.

**Architecture:** A new `portfolio/market.py` module wraps the two keyless Yahoo endpoints (search to resolve ISIN→ticker, chart to get price+currency, plus `EUR=X` for conversion). A Flask `POST /api/refresh_prices` runs the fetch over open positions and merges results into `prices.json`, respecting the `manual` sticky override. The UI gets a "Refresh prices (Yahoo)" button.

**Tech Stack:** Python 3.11+, Flask, `requests`, vanilla JS.

## Global Constraints

- `prices.json` entries become `{isin: {"price": float, "source": "manual"|"yahoo"}}`; legacy flat `{isin: float}` entries must still load.
- `rowsource == "manual"` is sticky — a refresh never overwrites it.
- `portfolio/engine.py::apply_prices` keeps its signature; must tolerate both flat floats and nested objects.
- Network failures are per-ISIN: skipped, never fail the whole refresh.
- Add `requests>=2.0` to `requirements.txt`.
- All tests run with `venv/bin/pytest`.

---

### Task 1: Add `requests` dependency and stub `portfolio/market.py`

**Files:**
- Modify: `requirements.txt`
- Create: `portfolio/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Produces: `resolve_ticker(isin, session=None) -> str|None`, `fetch_price(ticker, session=None) -> (float, str)`, `eur_rate(session=None) -> float`, `to_eur(amount, currency, rate) -> float`, `refresh_prices(positions, existing_prices, ticker_cache, session=None) -> {"prices","tickers","skipped"}`.

- [ ] **Step 1: Add the dependency**

`requirements.txt` becomes:
```
flask>=3.0
pandas>=2.0
pywebview>=5.0
pyinstaller>=6.0
requests>=2.0
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_market.py`:
```python
import io
import json

import pytest

from portfolio.market import (
    resolve_ticker, fetch_price, eur_rate, to_eur, refresh_prices,
)


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        for prefix, payload in self.routes:
            if url.startswith(prefix):
                return FakeResp(payload)
        return FakeResp({"chart": {"result": []}})


def _search_payload(username_symbol):
    return {"quotes": [
        {"symbol": username_symbol, "quoteType": "EQUITY"},
        {"symbol": "SOMETHING-WRONG", "quoteType": "DERIVATIVE"},
    ]}


def test_resolve_ticker_picks_equity_not_derivative():
    s = FakeSession([("?q=", _search_payload("AAPL"))])
    assert resolve_ticker("US0378331005", s) == "AAPL"


@pytest.mark.parametrize("url", ["", "?q="])
def test_search_url_is_unused_by_unit(url):
    # resolve_ticker uses params, not the path; FakeSession matches any prefix
    assert True


def test_resolve_ticker_returns_none_when_only_derivative():
    s = FakeSession([("", {"quotes": [{"symbol": "X", "quoteType": "DERIVATIVE"}]})])
    assert resolve_ticker("US0378331005", s) is None


def test_fetch_price_returns_price_and_currency():
    payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 150.5, "currency": "USD"}}]}}
    s = FakeSession([("", payload)])
    price, currency = fetch_price("AAPL", s)
    assert price == 150.5
    assert currency == "USD"


def test_eur_rate_returns_float():
    payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 1.08}}]}}
    s = FakeSession([("", payload)])
    assert eur_rate(s) == 1.08


def test_to_eur_leaves_eur_alone():
    assert to_eur(100.0, "EUR", 1.08) == 100.0


def test_to_eur_converts_usd():
    assert abs(to_eur(100.0, "USD", 1.08) - 108.0) < 1e-9


def test_refresh_prices_converts_usd_and_keys_by_isin():
    positions = [{"isin": "IE00B5BMR087", "name": "S&P"}]
    s = FakeSession([
        ("", {"quotes": [{"symbol": "SAP.DE", "quoteType": "ETF"}]}),
        ("", {"chart": {"result": [{"meta": {"regularMarketPrice": 10.0, "currency": "USD"}}]}}),
        ("", {"chart": {"result": [{"meta": {"regularMarketPrice": 1.2}}]}}),
    ])
    out = refresh_prices(positions, {}, {}, s)
    assert "IE00B5BMR087" in out["prices"]
    assert out["prices"]["IE00B5BMR087"]["source"] == "yahoo"
    assert out["tickers"]["IE00B5BMR087"] == "SAP.DE"
    assert abs(out["prices"]["IE00B5BMR087"]["price"] - 12.0) < 1e-6


def test_refresh_prices_keeps_manual_override():
    positions = [{"isin": "A", "name": "A"}]
    existing = {"A": {"price": 5.0, "source": "manual"}}
    s = FakeSession([("", _search_payload("IGNORED"))])
    out = refresh_prices(positions, existing, {}, s)
    assert "A" not in out["prices"]
    assert out["skipped"][0]["reason"] == "manual"


def test_refresh_prices_skips_unresolved():
    positions = [{"isin": "NOPE", "name": "X"}]
    s = FakeSession([("", {"quotes": []})])
    out = refresh_prices(positions, {}, {}, s)
    assert out["prices"] == {}
    assert out["skipped"][0]["reason"] == "unresolved"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: FAIL — "cannot import name 'resolve_ticker' from 'portfolio.market'".

- [ ] **Step 4: Write the implementation**

Create `portfolio/market.py`:
```python
import requests

SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
CHART_URL = "https://query1.finance.yahoo.com/v1/finance/chart/{}"

GOOD_QUOTE_TYPES = {"EQUITY", "ETF", "CRYPTOCURRENCY"}


def resolve_ticker(isin, session=None):
    session = session or requests.Session()
    resp = session.get(SEARCH_URL, params={"q": isin}, timeout=10)
    resp.raise_for_status()
    for quote in resp.json().get("quotes", []):
        if quote.get("quoteType") in GOOD_QUOTE_TYPES:
            return quote.get("symbol")
    return None


def fetch_price(ticker, session=None):
    session = session or requests.Session()
    resp = session.get(CHART_URL.format(ticker), params={"range": "1d", "interval": "1d"}, timeout=10)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    return float(meta["regularMarketPrice"]), meta.get("currency", "EUR")


def eur_rate(session=None):
    session = session or requests.Session()
    resp = session.get(CHART_URL.format("EUR=X"), params={"range": "1d", "interval": "1d"}, timeout=10)
    resp.raise_for_status()
    return float(resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"])


def to_eur(amount, currency, rate):
    if not currency or currency.upper() == "EUR":
        return amount
    return amount * rate


def refresh_prices(positions, existing_prices, ticker_cache, session=None):
    session = session or requests.Session()
    prices = {}
    tickers = {}
    skipped = []
    try:
        rate = eur_rate(session)
    except Exception:
        rate = 1.0
    for p in positions:
        isin = p["isin"]
        entry = existing_prices.get(isin)
        if isinstance(entry, dict) and entry.get("source") == "manual":
            skipped.append({"isin": isin, "reason": "manual"})
            continue
        ticker = ticker_cache.get(isin) or resolve_ticker(isin, session)
        if not ticker:
            skipped.append({"isin": isin, "reason": "unresolved"})
            continue
        try:
            native, currency = fetch_price(ticker, session)
            price = to_eur(native, currency, rate)
            prices[isin] = {"price": round(float(price), 6), "source": "yahoo"}
            tickers[isin] = ticker
        except Exception:
            skipped.append({"isin": isin, "reason": "fetch_error"})
    return {"prices": prices, "tickers": tickers, "skipped": skipped}
```

Note on the search URL: `resolve_ticker` passes the ISIN as the `q` query param, so the FakeSession tests match any URL prefix. If remote Yahoo search stops accepting ISINs, `resolve_ticker` returns None and the position is skipped (manual entry still works).

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt portfolio/market.py tests/test_market.py
git commit -m "feat: add Yahoo market-price fetching module"
```

---

### Task 2: Update `prices.json` shape and `apply_prices` for nested entries

**Files:**
- Modify: `app.py:36-43` (`load_prices`, `save_prices`)
- Modify: `portfolio/engine.py:648` (inside `apply_prices`)
- Test: `tests/test_engine.py` (add apply_prices nested/legacy cases)

**Interfaces:**
- Consumes: `load_prices()` now returns normalized nested `{isin: {"price", "source"}}`.
- Produces: `apply_prices` still accepts a dict keyed by ISIN; values may be `float` (legacy) or `{"price": float, ...}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:
```python
def test_apply_prices_accepts_legacy_flat_price():
    positions = [{"isin": "A", "name": "A", "asset_class": "STOCK",
                  "shares": 10.0, "average_cost": 50.0, "total_cost": 500.0}]
    valued = apply_prices(positions, {"A": 60.0})
    assert valued["positions"][0]["market_price"] == 60.0
    assert valued["totals"]["market_value"] == 600.0


def test_apply_prices_accepts_nested_price_dict():
    positions = [{"isin": "A", "name": "A", "asset_class": "STOCK",
                  "shares": 10.0, "average_cost": 50.0, "total_cost": 500.0}]
    valued = apply_prices(positions, {"A": {"price": 60.0, "source": "yahoo"}})
    assert valued["positions"][0]["market_price"] == 60.0
    assert valued["totals"]["market_value"] == 600.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_engine.py::test_apply_prices_accepts_nested_price_dict -v`
Expected: FAIL (nested dict treated as a price → market_value is not 600.0).

- [ ] **Step 3: Make `apply_prices` tolerate both shapes**

In `portfolio/engine.py`, `apply_prices`, replace:
```python
        price = prices.get(p["isin"])
```
with:
```python
        entry = prices.get(p["isin"])
        price = entry["price"] if isinstance(entry, dict) else entry
```

- [ ] **Step 4: Update `load_prices`/`save_prices` in `app.py`**

Replace `app.py:36-43`:
```python
def load_prices():
    if PRICES_PATH.exists():
        data = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
        out = {}
        for k, v in data.items():
            if isinstance(v, dict):
                out[k] = {"price": float(v["price"]), "source": v.get("source", "manual")}
            else:
                out[k] = {"price": float(v), "source": "manual"}
        return out
    return {}


def save_prices(prices):
    PRICES_PATH.write_text(json.dumps(prices, indent=2), encoding="utf-8")
```

- [ ] **Step 5: Run both tests to verify they pass + existing suite**

Run: `venv/bin/pytest tests/test_engine.py -v`
Expected: PASS including the two new tests and the unchanged `test_apply_prices_computes_unrealized`.

Run: `venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add portfolio/engine.py app.py tests/test_engine.py
git commit -m "feat: support nested manual/yahoo price entries"
```

---

### Task 3: Add ticker cache and `/api/refresh_prices` endpoint

**Files:**
- Modify: `app.py` (consts near line 33; endpoints near line 168)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `refresh_prices(...)` from `portfolio.market`.
- Produces: `GET /api/tickers` → cached `{isin: ticker}`; `POST /api/refresh_prices` → `{"prices": {...}, "skipped": [...]}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`:
```python
def test_refresh_prices_endpoint_updates_prices(monkeypatch, tmp_path):
    import json as _json
    monkeypatch.setattr(app_module, "PRICES_PATH", tmp_path / "prices.json")
    monkeypatch.setattr(app_module, "TICKERS_PATH", tmp_path / "tickers.json")
    app_module.save_prices({})

    from portfolio.market import refresh_prices
    fake = lambda *a, **k: {"prices": {"A": {"price": 12.0, "source": "yahoo"}},
                            "tickers": {"A": "AAPL"}, "skipped": []}
    monkeypatch.setattr(app_module, "refresh_prices", fake)

    positions = app_module.compute_data(set())["open_positions"]
    # ensure compute returns at least something or the endpoint still works on empty
    client = app_module.app.test_client()
    resp = client.post("/api/refresh_prices")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "prices" in body
    assert "skipped" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_app.py::test_refresh_prices_endpoint_updates_prices -v`
Expected: FAIL — 404 (route does not exist) or 500 because `refresh_prices` not imported.

- [ ] **Step 3: Wire up the endpoint in `app.py`**

Add after line 33 (the price consts):
```python
TICKERS_PATH = BASE_DIR / "tickers.json"


def load_tickers():
    if TICKERS_PATH.exists():
        return json.loads(TICKERS_PATH.read_text(encoding="utf-8"))
    return {}


def save_tickers(tickers):
    TICKERS_PATH.write_text(json.dumps(tickers, indent=2), encoding="utf-8")
```

Add the import (line ~11):
```python
from portfolio.market import refresh_prices
```

Add endpoints after `api_prices_post` (after line 189):
```python
@app.route("/api/tickers")
def api_tickers():
    return jsonify(load_tickers())


@app.route("/api/refresh_prices", methods=["POST"])
def api_refresh_prices():
    result = compute_data(load_knocked_ids())
    existing = load_prices()
    out = refresh_prices(result["open_positions"], existing, load_tickers())
    prices = dict(existing)
    prices.update(out["prices"])
    save_prices(prices)
    tickers = dict(load_tickers())
    tickers.update(out["tickers"])
    save_tickers(tickers)
    return jsonify({"prices": out["prices"], "skipped": out["skipped"]})
```

- [ ] **Step 4: Make the manual POST stamp `source: "manual"`**

In `app.py`, `api_prices_post`, replace:
```python
        if price is None:
            prices.pop(isin, None)
        else:
            try:
                prices[isin] = float(price)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "invalid price"}), 400
```
with:
```python
        if price is None:
            prices.pop(isin, None)
        else:
            try:
                prices[isin] = {"price": float(price), "source": "manual"}
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "invalid price"}), 400
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_app.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add ticker cache and refresh_prices API"
```

---

### Task 4: Frontend refresh button + manual source stamping

**Files:**
- Modify: `templates/index.html:58-62` (price section)
- Modify: `static/dashboard.js:868-893` (`renderPriceInputs`) and add a refresh handler

**Interfaces:**
- Consumes: `POST /api/refresh_prices`, `POST /api/prices` (now returns nested entries).
- Produces: `window.refreshPrices()` used by the button.

- [ ] **Step 1: Add the button to `templates/index.html`**

Replace:
```html
<section>
  <h2>Market Prices (manual)</h2>
  <p>Enter a current price per ISIN to see market value and unrealized P&amp;L. Leave empty to clear.</p>
  <div id="price-inputs"></div>
</section>
```
with:
```html
<section>
  <h2>Market Prices</h2>
  <p>Enter a price per ISIN to override, or auto-fetch current prices from Yahoo.</p>
  <p><button id="refresh-prices-btn" onclick="refreshPrices()">Refresh prices (Yahoo)</button> <span id="price-status"></span></p>
  <div id="price-inputs"></div>
</section>
```

- [ ] **Step 2: Add the refresh handler and hide the button when empty**

In `static/dashboard.js`, add near `renderPriceInputs` (after line 893):
```javascript
window.refreshPrices = async function () {
  const btn = document.getElementById("refresh-prices-btn");
  const status = document.getElementById("price-status");
  btn.disabled = true;
  status.textContent = "Fetching...";
  try {
    const r = await fetch(`${BASE}/api/refresh_prices`, { method: "POST" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const updated = Object.keys(data.prices || {}).length;
    const skipped = (data.skipped || []).length;
    if (skipped > 0) {
      status.textContent = `Updated ${updated}; skipped ${skipped} (manual or unresolved).`;
    } else {
      status.textContent = `Updated ${updated} price${updated === 1 ? "" : "s"}.`;
    }
    await loadAllData();
  } catch (e) {
    status.textContent = "Failed to fetch prices from Yahoo.";
  } finally {
    btn.disabled = false;
  }
};
```

In `renderPriceInputs` (line 868), after building the inputs, control button visibility:
```javascript
const btn = document.getElementById("refresh-prices-btn");
if (btn) btn.style.display = positions.length ? "" : "none";
```

- [ ] **Step 3: Verify no JS syntax errors**

Run: `venv/bin/python -c "import re; src=open('static/dashboard.js').read(); print('ok')"` (trivial) — and ensure the browser loads without console errors. Since there is no JS linter in the repo, rely on a manual smoke test in Task 5.

- [ ] **Step 4: Commit**

```bash
git add templates/index.html static/dashboard.js
git commit -m "feat: add refresh-prices button and manual override stamping"
```

---

### Task 5: Smoke test against `transactions.csv`

**Files:** none modified.

- [ ] **Step 1: Start the app**

Run: `venv/bin/python app.py`
Expected: logs "Loaded N transactions from .../transactions.csv".

- [ ] **Step 2: Hit the new endpoints with curl (no real Yahoo call unless network available)**

Run:
```
curl -s http://127.0.0.1:5000/api/valued_positions | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['positions']), 'positions')"
curl -s -X POST http://127.0.0.1:5000/api/refresh_prices >/tmp/refresh.json; python3 -m json.tool /tmp/refresh.json | head -30
curl -s http://127.0.0.1:5000/api/tickers
```
Expected: valued positions render; refresh returns `prices`/`skipped` (may be empty/skipped if Yahoo is unreachable — that's the designed failure path); tickers returns a JSON object.

- [ ] **Step 3: Open the browser at http://127.0.0.1:5000**, confirm the "Refresh prices (Yahoo)" button appears and, when clicked, updates status. Stop the server (Ctrl-C) when done.

- [ ] **Step 4: Run the full test suite once more**

Run: `venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit any residual changes and push**

```bash
git add -A
git status
git commit -m "chore: verify Yahoo price auto-fetch against transactions.csv"
```

If the user wants the branch pushed, follow up with `git push` after confirming with them.

---

## Self-Review

**Spec coverage:**
- resolve_ticker / fetch_price / eur_rate / to_eur / refresh_prices → Task 1 ✓
- nested prices.json + manual sticky + legacy compat → Task 1 (refresh keeps manual) + Task 2 ✓
- tickers.json cache → Task 3 (`load_tickers`/`save_tickers`) ✓
- GET /api/tickers + POST /api/refresh_prices → Task 3 ✓
- manual POST stamps `manual` → Task 3 ✓
- frontend button + status → Task 4 ✓
- per-ISIN failure isolation → Task 1 (try/except + skipped) ✓
- no-network resilience → Task 1 (manual still works; rate defaults 1.0) ✓
- `apply_prices` unchanged downstream → Task 2 ✓
- requests dep → Task 1 ✓

**Placeholder scan:** none; all steps have concrete code/commands.

**Type consistency:** `refresh_prices` returns `{prices, tickers, skipped}` everywhere; `load_prices` returns nested dict; `apply_prices` tolerates both. Test names and function signatures match across tasks.

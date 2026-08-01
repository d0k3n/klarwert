# Finnhub Price Auto-Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken Yahoo Finance price fetch with Finnhub so "Refresh prices" works again, and disable the feature entirely when no `FINNHUB_API_KEY` is configured.

**Architecture:** Rewrite `portfolio/market.py` around Finnhub's three endpoints — `search?q=<isin>` resolves ISIN→ticker, `quote` returns the live price, `stock/profile2` (best-effort, free-tier-gated) plus ticker-suffix inference supply the native currency. Frankfurter's any-base FX API replaces the old USD-only `eur_rate`, so all instrument currencies convert to EUR correctly. `app.py` gates the feature on key presence; the frontend hides/disables the button when no key is set.

**Tech Stack:** Python 3.11+, Flask, `requests` (already a dependency), vanilla JS.

## Global Constraints

- `prices.json` entries are `{isin: {"price": float, "source": "manual"|"auto"}}`; legacy flat `{isin: float}` and `"yahoo"`-source entries must still load and be overwritable.
- `source == "manual"` is sticky — a refresh never overwrites it.
- No key configured → `refresh_prices` returns `{"disabled": True, ...}`; `POST /api/refresh_prices` returns `{"enabled": False, "reason": "no_api_key"}`; the UI shows the button disabled.
- API key comes from `FINNHUB_API_KEY` env var, falling back to a gitignored `.env` in the project root (simple `KEY=VALUE` lines). Never hardcoded.
- Network failures are per-ISIN: skipped with a reason, never fail the whole refresh.
- Free tier = 60 requests/min → `refresh_prices` takes a `delay` param (default 1.1s) and tests pass `delay=0`.
- `requests>=2.0` already in `requirements.txt` — no dependency change.
- All tests run with `venv/bin/pytest`.

---

### Task 1: Config loading, `.env`, `.gitignore`, README

**Files:**
- Create: `portfolio/market.py`
- Modify: `.gitignore`
- Modify: `README.md`
- Test: `tests/test_market.py`

**Interfaces:**
- Produces: `get_api_key() -> str | None`, `is_configured() -> bool`. Nothing else in the module yet.

- [ ] **Step 1: Add `.env` to `.gitignore`**

Append to `.gitignore`:
```
.env
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_market.py`:
```python
import pytest

from portfolio.market import get_api_key, is_configured


@pytest.fixture(autouse=True)
def _no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setattr("portfolio.market.ENV_PATH", tmp_path / "no-dotenv")


def test_get_api_key_reads_env(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "env-key")
    assert get_api_key() == "env-key"


def test_get_api_key_reads_dotenv(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text('FINNHUB_API_KEY="dotenv-key"\n', encoding="utf-8")
    monkeypatch.setattr("portfolio.market.ENV_PATH", env)
    assert get_api_key() == "dotenv-key"


def test_get_api_key_none_when_unset():
    assert get_api_key() is None


def test_is_configured_false_without_key():
    assert is_configured() is False


def test_is_configured_true_with_key(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    assert is_configured() is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio.market'`.

- [ ] **Step 4: Implement config in `portfolio/market.py`**

Create `portfolio/market.py`:
```python
import os
from pathlib import Path

import requests

FINNHUB_BASE = "https://finnhub.io/api/v1"
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_dotenv():
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_api_key():
    _load_dotenv()
    return os.environ.get("FINNHUB_API_KEY") or None


def is_configured():
    return bool(get_api_key())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: 5 passed.

- [ ] **Step 6: Update README**

In `README.md`, replace the sentence "No external data services or API keys are needed." under **Requirements** with:

```markdown
Live price auto-fetch is optional and uses Finnhub's free tier. To enable it,
create a `.env` file in the project root with your free API key:

```
FINNHUB_API_KEY=your_key_here
```

Get a key at https://finnhub.io/register. Without it, the price-refresh button is
disabled and manual price entry is still available. All computation stays local.
```

- [ ] **Step 7: Commit**

```bash
git add portfolio/market.py tests/test_market.py .gitignore README.md
git commit -m "feat: Finnhub API key config with .env fallback"
```

---

### Task 2: ISIN→ticker resolution via Finnhub search

**Files:**
- Modify: `portfolio/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: `get_api_key()` (Task 1).
- Produces: `GOOD_TYPES: set[str]`, `resolve_ticker(isin: str, session=None) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_market.py`:
```python
from portfolio.market import resolve_ticker


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
        for key, payload in self.routes:
            if key in url:
                return FakeResp(payload)
        return FakeResp({"count": 0, "result": []})


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")


def _search(symbol, type_):
    return {"count": 1, "result": [{"symbol": symbol, "type": type_}]}


def test_resolve_picks_stock_not_derivative(keyed):
    s = FakeSession([("/search", {
        "count": 2,
        "result": [
            {"symbol": "AAPL", "type": "Common Stock"},
            {"symbol": "WRONG", "type": "Option"},
        ],
    })])
    assert resolve_ticker("US0378331005", s) == "AAPL"


def test_resolve_accepts_etp(keyed):
    s = FakeSession([("/search", _search("CSPX.L", "ETP"))])
    assert resolve_ticker("IE00B5BMR087", s) == "CSPX.L"


def test_resolve_returns_none_when_no_result(keyed):
    s = FakeSession([("/search", {"count": 0, "result": []})])
    assert resolve_ticker("NOPE", s) is None


def test_resolve_returns_none_when_only_derivative(keyed):
    s = FakeSession([("/search", _search("DE000FD8B5S9", "Warrant"))])
    assert resolve_ticker("DE000FD8B5S9", s) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: 4 new FAILs with `ImportError: cannot import name 'resolve_ticker'`.

- [ ] **Step 3: Implement `resolve_ticker`**

In `portfolio/market.py`, add after `is_configured`:
```python
SEARCH_PATH = "/search"

GOOD_TYPES = {"Common Stock", "ETP", "Fund", "Depositary Receipt"}


def _finnhub_get(session, path, params):
    key = get_api_key()
    if not key:
        raise RuntimeError("Finnhub API key not configured")
    resp = session.get(FINNHUB_BASE + path, params=dict(params, token=key), timeout=10)
    resp.raise_for_status()
    return resp


def resolve_ticker(isin, session=None):
    session = session or requests.Session()
    resp = _finnhub_get(session, SEARCH_PATH, {"q": isin})
    for quote in resp.json().get("result", []):
        if quote.get("type") in GOOD_TYPES:
            return quote.get("symbol")
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add portfolio/market.py tests/test_market.py
git commit -m "feat: resolve ISIN to ticker via Finnhub search"
```

---

### Task 3: Price + currency via Finnhub quote and profile2/suffix

**Files:**
- Modify: `portfolio/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: `_finnhub_get` (Task 2).
- Produces: `fetch_price(ticker: str, session=None) -> (float, str)` — native price and currency code; `_profile_currency(session, ticker) -> str | None`; `_infer_currency(ticker) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_market.py`:
```python
from portfolio.market import fetch_price, _infer_currency


def test_fetch_price_returns_price_and_profile_currency(keyed):
    s = FakeSession([
        ("/quote", {"c": 150.5}),
        ("/stock/profile2", {"currency": "USD"}),
    ])
    price, currency = fetch_price("AAPL", s)
    assert price == 150.5
    assert currency == "USD"


def test_fetch_price_infers_suffix_currency_when_profile_blocked(keyed):
    s = FakeSession([
        ("/quote", {"c": 10.0}),
        ("/stock/profile2", {"error": "You don't have access to this resource."}),
    ])
    price, currency = fetch_price("CSPX.L", s)
    assert price == 10.0
    assert currency == "GBP"


def test_fetch_price_infers_usd_for_bare_symbol(keyed):
    s = FakeSession([
        ("/quote", {"c": 20.0}),
        ("/stock/profile2", {"error": "blocked"}),
    ])
    _, currency = fetch_price("NFLX", s)
    assert currency == "USD"


def test_infer_currency_suffixes():
    assert _infer_currency("SAP.DE") == "EUR"
    assert _infer_currency("NOVO B.CO") == "DKK"
    assert _infer_currency("VOW.DE") == "EUR"
    assert _infer_currency("AAPL") == "USD"
    assert _infer_currency("7203.T") == "JPY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: 5 new FAILs with `ImportError: cannot import name 'fetch_price'`.

- [ ] **Step 3: Implement price + currency**

In `portfolio/market.py`, add after `resolve_ticker`:
```python
QUOTE_PATH = "/quote"
PROFILE_PATH = "/stock/profile2"

_SUFFIX_CURRENCY = {
    ".L": "GBP", ".DE": "EUR", ".F": "EUR", ".BE": "EUR",
    ".PA": "EUR", ".AS": "EUR", ".MI": "EUR", ".CO": "DKK",
    ".T": "JPY", ".TO": "CAD", ".HK": "HKD",
}


def _profile_currency(session, ticker):
    try:
        resp = _finnhub_get(session, PROFILE_PATH, {"symbol": ticker})
        return resp.json().get("currency")
    except Exception:
        return None


def _infer_currency(ticker):
    return _SUFFIX_CURRENCY.get("." + ticker.rsplit(".", 1)[-1].upper(), "USD")


def fetch_price(ticker, session=None):
    session = session or requests.Session()
    resp = _finnhub_get(session, QUOTE_PATH, {"symbol": ticker})
    data = resp.json()
    if "c" not in data:
        raise ValueError(f"no quote for {ticker}")
    price = float(data["c"])
    currency = _profile_currency(session, ticker) or _infer_currency(ticker)
    return price, currency
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add portfolio/market.py tests/test_market.py
git commit -m "feat: fetch price and currency via Finnhub quote/profile"
```

---

### Task 4: FX conversion to EUR via Frankfurter (any base)

**Files:**
- Modify: `portfolio/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: `requests` session with a `_fx_cache` dict attribute (invented here).
- Produces: `fx_rate(currency: str, session=None) -> float`, `to_eur(amount: float, currency: str, session=None) -> float`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_market.py`:
```python
from portfolio.market import fx_rate, to_eur


def _fx_routes():
    return [("api.frankfurter.dev", {"rates": {"EUR": 1.08}})]


def test_fx_rate_returns_eur_for_eur():
    s = FakeSession([])
    assert fx_rate("EUR", s) == 1.0


def test_fx_rate_fetches_and_caches(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "unused")
    s = FakeSession(_fx_routes())
    assert fx_rate("USD", s) == 1.08
    assert fx_rate("USD", s) == 1.08
    assert len(s.calls) == 1  # cached, no second network call


def test_to_eur_leaves_eur_alone():
    s = FakeSession([])
    assert to_eur(100.0, "EUR", s) == 100.0


def test_to_eur_converts_usd():
    s = FakeSession(_fx_routes())
    assert abs(to_eur(100.0, "USD", s) - 108.0) < 1e-9


def test_to_eur_converts_gbp(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "unused")
    s = FakeSession([("api.frankfurter.dev", {"rates": {"EUR": 1.1686}})])
    assert abs(to_eur(100.0, "GBP", s) - 116.86) < 1e-9


def test_to_eur_handles_missing_currency():
    s = FakeSession([])
    assert to_eur(100.0, "", s) == 100.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: 6 new FAILs with `ImportError: cannot import name 'fx_rate'`.

- [ ] **Step 3: Implement FX**

In `portfolio/market.py`, add after `fetch_price`:
```python
def fx_rate(currency, session=None):
    session = session or requests.Session()
    cur = (currency or "EUR").upper()
    if cur == "EUR":
        return 1.0
    cache = getattr(session, "_fx_cache", None)
    if cache is None:
        cache = session._fx_cache = {}
    if cur in cache:
        return cache[cur]
    resp = session.get(FRANKFURTER_URL, params={"base": cur, "symbols": "EUR"}, timeout=10)
    resp.raise_for_status()
    rate = float(resp.json()["rates"]["EUR"])
    cache[cur] = rate
    return rate


def to_eur(amount, currency, session=None):
    return amount * fx_rate(currency, session)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add portfolio/market.py tests/test_market.py
git commit -m "feat: convert any currency to EUR via Frankfurter FX"
```

---

### Task 5: `refresh_prices` orchestration with disabled state and rate limiting

**Files:**
- Modify: `portfolio/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Consumes: `is_configured` (Task 1), `resolve_ticker` (Task 2), `fetch_price` (Task 3), `to_eur` (Task 4).
- Produces: `refresh_prices(positions, existing_prices, ticker_cache, session=None, delay=1.1) -> {"prices","tickers","skipped"} | {"disabled": True, ...}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_market.py`:
```python
import portfolio.market as market
from portfolio.market import refresh_prices


def test_refresh_disabled_without_key(monkeypatch):
    monkeypatch.setattr(market, "get_api_key", lambda: None)
    s = FakeSession([])
    out = refresh_prices([{"isin": "A", "name": "A"}], {}, {}, s, delay=0)
    assert out["disabled"] is True


def test_refresh_converts_usd_and_keys_by_isin(keyed):
    positions = [{"isin": "IE00B5BMR087", "name": "S&P"}]
    s = FakeSession([
        ("/search", _search("CSPX.L", "ETP")),
        ("/quote", {"c": 10.0}),
        ("/stock/profile2", {"currency": "USD"}),
        ("api.frankfurter.dev", {"rates": {"EUR": 1.08}}),
    ])
    out = refresh_prices(positions, {}, {}, s, delay=0)
    assert out["prices"]["IE00B5BMR087"]["source"] == "auto"
    assert out["tickers"]["IE00B5BMR087"] == "CSPX.L"
    assert abs(out["prices"]["IE00B5BMR087"]["price"] - 10.8) < 1e-6


def test_refresh_does_not_overwrite_manual(keyed):
    positions = [{"isin": "A", "name": "A"}]
    existing = {"A": {"price": 5.0, "source": "manual"}}
    s = FakeSession([("/search", _search("IGNORED", "Common Stock"))])
    out = refresh_prices(positions, existing, {}, s, delay=0)
    assert "A" not in out["prices"]
    assert any(item["reason"] == "manual" for item in out["skipped"])


def test_refresh_skips_unresolved(keyed):
    positions = [{"isin": "NOPE", "name": "X"}]
    s = FakeSession([("/search", {"count": 0, "result": []})])
    out = refresh_prices(positions, {}, {}, s, delay=0)
    assert out["prices"] == {}
    assert out["skipped"][0]["reason"] == "unresolved"


def test_refresh_reuses_ticker_cache(keyed):
    positions = [{"isin": "A", "name": "A"}]
    s = FakeSession([
        ("/quote", {"c": 9.0}),
        ("/stock/profile2", {"currency": "EUR"}),
    ])
    out = refresh_prices(positions, {}, {"A": "AAPL"}, s, delay=0)
    assert out["tickers"]["A"] == "AAPL"
    assert not any("/search" in url for url, _ in s.calls)


class RaisingResp(FakeResp):
    def raise_for_status(self):
        raise Exception("HTTP 429")


class RaisingSession(FakeSession):
    def get(self, url, params=None, timeout=None):
        return RaisingResp({"count": 0})


def test_refresh_isolates_network_failure_per_isin(keyed):
    positions = [{"isin": "A", "name": "A"}, {"isin": "B", "name": "B"}]
    s = RaisingSession([])
    out = refresh_prices(positions, {}, {}, s, delay=0)
    assert out["prices"] == {}
    assert len(out["skipped"]) == 2
    assert all(item["reason"] == "fetch_error" for item in out["skipped"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_market.py -v`
Expected: 6 new FAILs with `ImportError: cannot import name 'refresh_prices'`.

- [ ] **Step 3: Implement `refresh_prices`**

First, change the top of `portfolio/market.py` so the imports read:
```python
import os
import time
from pathlib import Path

import requests
```

Then append `refresh_prices` at the end of `portfolio/market.py`:
```python
def refresh_prices(positions, existing_prices, ticker_cache, session=None, delay=1.1):
    if not is_configured():
        return {"disabled": True, "prices": {}, "tickers": {}, "skipped": []}
    session = session or requests.Session()
    prices = {}
    tickers = {}
    skipped = []
    for p in positions:
        isin = p["isin"]
        entry = existing_prices.get(isin)
        if isinstance(entry, dict) and entry.get("source") == "manual":
            skipped.append({"isin": isin, "reason": "manual"})
            continue
        try:
            ticker = ticker_cache.get(isin) or resolve_ticker(isin, session)
            if not ticker:
                skipped.append({"isin": isin, "reason": "unresolved"})
                continue
            native, currency = fetch_price(ticker, session)
            price = to_eur(native, currency, session)
            prices[isin] = {"price": round(float(price), 6), "source": "auto"}
            tickers[isin] = ticker
        except Exception as exc:
            skipped.append({"isin": isin, "reason": "fetch_error", "message": f"{type(exc).__name__}: {exc}"})
        if delay:
            time.sleep(delay)
    return {"prices": prices, "tickers": tickers, "skipped": skipped}
```

- [ ] **Step 4: Run the full test suite**

Run: `venv/bin/pytest tests/ -q`
Expected: all tests pass (the old Yahoo-based `tests/test_market.py` cases are replaced by the new Finnhub cases written in Tasks 1-5; the other test files are untouched).

- [ ] **Step 5: Commit**

```bash
git add portfolio/market.py tests/test_market.py
git commit -m "feat: refresh_prices orchestration over Finnhub with per-ISIN isolation"
```

---

### Task 6: App endpoints — disabled state and refresh status

**Files:**
- Modify: `app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `refresh_prices` and `is_configured` from `portfolio.market`.
- Produces: `POST /api/refresh_prices` returns `{"enabled": False, "reason": "no_api_key"}` when disabled; `GET /api/refresh_status` returns `{"enabled": bool}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:
```python
def test_refresh_prices_disabled_without_key(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "PRICES_PATH", tmp_path / "prices.json")
    monkeypatch.setattr(app_module, "refresh_prices", lambda *a, **k: {"disabled": True})
    app_module.df = _df()
    app_module.invalidate_cache()
    client = app_module.app.test_client()
    resp = client.post("/api/refresh_prices")
    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": False, "reason": "no_api_key"}


def test_refresh_status_reports_enabled(monkeypatch):
    monkeypatch.setattr(app_module, "is_configured", lambda: True)
    client = app_module.app.test_client()
    assert client.get("/api/refresh_status").get_json() == {"enabled": True}


def test_refresh_status_reports_disabled(monkeypatch):
    monkeypatch.setattr(app_module, "is_configured", lambda: False)
    client = app_module.app.test_client()
    assert client.get("/api/refresh_status").get_json() == {"enabled": False}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_app.py -v`
Expected: 3 new FAILs (`404` for `/api/refresh_status`, and the disabled POST returns 200 with `{"prices":...}`).

- [ ] **Step 3: Update imports and endpoints in `app.py`**

Change line 14 in `app.py`:
```python
from portfolio.market import refresh_prices, is_configured
```

Replace the `api_refresh_prices` route (lines 216-227) and add `api_refresh_status`:
```python
@app.route("/api/refresh_status")
def api_refresh_status():
    return jsonify({"enabled": is_configured()})


@app.route("/api/refresh_prices", methods=["POST"])
def api_refresh_prices():
    result = compute_data(load_knocked_ids())
    existing = load_prices()
    out = refresh_prices(result["open_positions"], existing, load_tickers())
    if out.get("disabled"):
        return jsonify({"enabled": False, "reason": "no_api_key"})
    prices = dict(existing)
    prices.update(out["prices"])
    save_prices(prices)
    tickers = dict(load_tickers())
    tickers.update(out["tickers"])
    save_tickers(tickers)
    return jsonify({"prices": out["prices"], "skipped": out["skipped"]})
```

- [ ] **Step 4: Update the existing merge test's source value**

In `tests/test_app.py`, update the `fake` in `test_refresh_prices_endpoint_merges_and_persists` so `"source": "yahoo"` becomes `"source": "auto"` in both the fake dict and the three assertions (`body["prices"]["B"]["source"]`, `saved["B"]`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: disable price refresh without API key; add refresh status endpoint"
```

---

### Task 7: Frontend — button label and disabled state

**Files:**
- Modify: `templates/index.html`
- Modify: `static/dashboard.js`

**Interfaces:**
- Consumes: `GET /api/refresh_status` (Task 6).
- Produces: refresh button disabled with a tooltip when no key; updated copy.

- [ ] **Step 1: Update `templates/index.html`**

Replace line 61 in `templates/index.html`:
```html
<p><button id="refresh-prices-btn" onclick="refreshPrices()">Refresh prices (Yahoo)</button> <span id="price-status"></span></p>
```
with:
```html
<p><button id="refresh-prices-btn" onclick="refreshPrices()">Refresh prices (Finnhub)</button> <span id="price-status"></span></p>
```

- [ ] **Step 2: Update `static/dashboard.js`**

In `renderPriceInputs`, replace the button display block (line 893-894):
```js
const btn = document.getElementById("refresh-prices-btn");
if (btn) btn.style.display = positions.length ? "" : "none";
```
with:
```js
const btn = document.getElementById("refresh-prices-btn");
if (btn) {
  btn.style.display = positions.length ? "" : "none";
  fetch(`${BASE}/api/refresh_status`).then(r => r.json()).then(s => {
    if (s.enabled === false) {
      btn.disabled = true;
      btn.title = "No Finnhub API key configured (set FINNHUB_API_KEY in .env)";
    }
  }).catch(() => {});
}
```

In `window.refreshPrices`, add a disabled-state short-circuit after `const data = await r.json();`:
```js
    const data = await r.json();
    if (data.enabled === false) {
      status.textContent = "Live prices disabled: no Finnhub API key configured.";
      return;
    }
```

Replace the final catch message "Failed to fetch prices from Yahoo." with "Failed to fetch prices."

- [ ] **Step 3: Verify no syntax errors**

Run: `node --check static/dashboard.js`
Expected: no output, exit 0.

- [ ] **Step 4: Run the full test suite**

Run: `venv/bin/pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 5: Manual smoke test**

Run: `venv/bin/python app.py` (or `./run.sh`), open http://127.0.0.1:5000, confirm:
- Without `.env`/env key: button present but disabled with tooltip.
- With key: clicking "Refresh prices (Finnhub)" updates the status line.

- [ ] **Step 6: Commit**

```bash
git add templates/index.html static/dashboard.js
git commit -m "feat: hide and disable price refresh when no Finnhub key is set"
```

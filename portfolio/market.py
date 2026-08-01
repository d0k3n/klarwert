import requests

YAHOO_HOSTS = ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]
SEARCH_PATH = "/v1/finance/search"
CHART_PATH = "/v8/finance/chart/{}"
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR"

GOOD_QUOTE_TYPES = {"EQUITY", "ETF", "CRYPTOCURRENCY"}

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def _yahoo_get(session, path, params):
    last = None
    for host in YAHOO_HOSTS:
        url = f"https://{host}{path}"
        try:
            resp = session.get(url, params=params, timeout=10, headers={"User-Agent": _UA})
            if resp.status_code == 200:
                return resp
            last = resp
        except Exception as exc:
            last = exc
    if last is not None:
        raise last if isinstance(last, Exception) else requests.HTTPError(f"HTTP {last.status_code}")
    raise requests.HTTPError("no Yahoo host reachable")


def resolve_ticker(isin, session=None):
    session = session or requests.Session()
    resp = _yahoo_get(session, SEARCH_PATH, {"q": isin})
    for quote in resp.json().get("quotes", []):
        if quote.get("quoteType") in GOOD_QUOTE_TYPES:
            return quote.get("symbol")
    return None


def fetch_price(ticker, session=None):
    session = session or requests.Session()
    resp = _yahoo_get(session, CHART_PATH.format(ticker), {"range": "1d", "interval": "1d"})
    meta = resp.json()["chart"]["result"][0]["meta"]
    return float(meta["regularMarketPrice"]), meta.get("currency", "EUR")


def eur_rate(session=None):
    session = session or requests.Session()
    try:
        resp = _yahoo_get(session, CHART_PATH.format("EUR=X"), {"range": "1d", "interval": "1d"})
        return float(resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        fx = session.get(FRANKFURTER_URL, timeout=10)
        fx.raise_for_status()
        return float(fx.json()["rates"]["EUR"])


def to_eur(amount, currency, rate):
    if not currency or currency.upper() == "EUR":
        return amount
    return amount * rate


def _warm_session(session):
    try:
        session.get("https://fc.yahoo.com", timeout=10, headers={"User-Agent": _UA})
    except Exception:
        pass
    return session


def refresh_prices(positions, existing_prices, ticker_cache, session=None):
    session = _warm_session(session or requests.Session())
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
        try:
            ticker = ticker_cache.get(isin) or resolve_ticker(isin, session)
            if not ticker:
                skipped.append({"isin": isin, "reason": "unresolved"})
                continue
            native, currency = fetch_price(ticker, session)
            price = to_eur(native, currency, rate)
            prices[isin] = {"price": round(float(price), 6), "source": "yahoo"}
            tickers[isin] = ticker
        except Exception:
            skipped.append({"isin": isin, "reason": "fetch_error"})
    return {"prices": prices, "tickers": tickers, "skipped": skipped}

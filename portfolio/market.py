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

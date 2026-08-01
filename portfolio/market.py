import os
import sys
import time
from pathlib import Path

import requests

FINNHUB_BASE = "https://finnhub.io/api/v1"
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"

if getattr(sys, "_MEIPASS", None):
    ENV_PATH = Path(os.environ.get("APPDATA", Path.home())) / "Klarwert" / ".env"
else:
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


def _redact_key(text):
    key = get_api_key()
    if key and key in text:
        return text.replace(key, "***")
    return text


SEARCH_PATH = "/search"

GOOD_TYPES = {"Common Stock", "ETP", "Fund", "Depositary Receipt"}


def _pace(session, delay):
    if not delay:
        return
    last = getattr(session, "_finnhub_last", 0.0)
    wait = last + delay - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    session._finnhub_last = time.monotonic()


def _finnhub_get(session, path, params):
    key = get_api_key()
    if not key:
        raise RuntimeError("Finnhub API key not configured")
    _pace(session, getattr(session, "_finnhub_delay", 0.0))
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
    inferred = _infer_currency(ticker)
    currency = inferred if inferred != "USD" else (_profile_currency(session, ticker) or inferred)
    return price, currency


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


def refresh_prices(positions, existing_prices, ticker_cache, session=None, delay=1.1):
    if not is_configured():
        return {"disabled": True, "prices": {}, "tickers": {}, "skipped": []}
    session = session or requests.Session()
    session._finnhub_delay = delay
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
            message = _redact_key(f"{type(exc).__name__}: {exc}")
            skipped.append({"isin": isin, "reason": "fetch_error", "message": message})
    return {"prices": prices, "tickers": tickers, "skipped": skipped}

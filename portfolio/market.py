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

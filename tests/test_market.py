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
    def __init__(self, responses):
        self.responses = list(responses)
        self.i = 0
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if self.i < len(self.responses):
            payload = self.responses[self.i]
        else:
            payload = {"quotes": [], "chart": {"result": []}}
        self.i += 1
        return FakeResp(payload)


def _search(best_symbol, best_type="EQUITY"):
    return {"quotes": [
        {"symbol": best_symbol, "quoteType": best_type},
        {"symbol": "WRONG", "quoteType": "DERIVATIVE"},
    ]}


def test_resolve_ticker_picks_equity_not_derivative():
    s = FakeSession([_search("AAPL")])
    assert resolve_ticker("US0378331005", s) == "AAPL"


def test_resolve_ticker_returns_none_when_only_derivative():
    s = FakeSession([{"quotes": [{"symbol": "WRONG", "quoteType": "DERIVATIVE"}]}])
    assert resolve_ticker("US0378331005", s) is None


def test_resolve_ticker_returns_none_when_no_quotes():
    s = FakeSession([{"quotes": []}])
    assert resolve_ticker("UNKNOWN1", s) is None


@pytest.mark.parametrize("cursor,typ", [("SAP.DE", "ETF"), ("BTC-USD", "CRYPTOCURRENCY")])
def test_resolve_ticker_accepts_etf_and_crypto(cursor, typ):
    s = FakeSession([_search(cursor, typ)])
    assert resolve_ticker("IE00B5BMR087", s) == cursor


def test_fetch_price_returns_price_and_currency():
    payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 150.5, "currency": "USD"}}]}}
    price, currency = fetch_price("AAPL", FakeSession([payload]))
    assert price == 150.5
    assert currency == "USD"


def test_eur_rate_returns_float():
    payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 1.08}}]}}
    assert eur_rate(FakeSession([payload])) == 1.08


def test_to_eur_leaves_eur_alone():
    assert to_eur(100.0, "EUR", 1.08) == 100.0


def test_to_eur_converts_usd():
    assert abs(to_eur(100.0, "USD", 1.08) - 108.0) < 1e-9


def test_to_eur_handles_missing_currency():
    assert to_eur(100.0, "", 1.08) == 100.0


def test_refresh_converts_usd_and_keys_by_isin():
    positions = [{"isin": "IE00B5BMR087", "name": "S&P"}]
    s = FakeSession([
        {"chart": {"result": [{"meta": {"regularMarketPrice": 1.2}}]}},                     # eur_rate
        _search("SAP.DE", "ETF"),                    # resolve_ticker
        {"chart": {"result": [{"meta": {"regularMarketPrice": 10.0, "currency": "USD"}}]}},  # price
    ])
    out = refresh_prices(positions, {}, {}, s)
    assert out["prices"]["IE00B5BMR087"]["source"] == "yahoo"
    assert out["tickers"]["IE00B5BMR087"] == "SAP.DE"
    assert abs(out["prices"]["IE00B5BMR087"]["price"] - 12.0) < 1e-6


def test_refresh_does_not_overwrite_manual():
    positions = [{"isin": "A", "name": "A"}]
    existing = {"A": {"price": 5.0, "source": "manual"}}
    s = FakeSession([_search("IGNORED")])
    out = refresh_prices(positions, existing, {}, s)
    assert "A" not in out["prices"]
    assert out["skipped"][0]["reason"] == "manual"


def test_refresh_skips_unresolved():
    positions = [{"isin": "NOPE", "name": "X"}]
    s = FakeSession([
        {"chart": {"result": [{"meta": {"regularMarketPrice": 1.0}}]}},  # eur_rate
        {"quotes": []},                                                  # resolve -> none
    ])
    out = refresh_prices(positions, {}, {}, s)
    assert out["prices"] == {}
    assert out["skipped"][0]["reason"] == "unresolved"


def test_refresh_reuses_ticker_cache():
    positions = [{"isin": "A", "name": "A"}]
    s = FakeSession([
        {"chart": {"result": [{"meta": {"regularMarketPrice": 1.0}}]}},  # eur_rate
        {"chart": {"result": [{"meta": {"regularMarketPrice": 9.0, "currency": "EUR"}}]}},
    ])
    out = refresh_prices(positions, {}, {"A": "AAPL"}, s)
    assert out["tickers"]["A"] == "AAPL"

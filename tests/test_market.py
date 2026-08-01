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

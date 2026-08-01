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


from portfolio.market import refresh_prices, to_eur


def test_refresh_prices_disabled_without_key():
    result = refresh_prices([{"isin": "A", "name": "A"}], {}, {})
    assert result == {"prices": {}, "tickers": {}, "skipped": [], "disabled": True}


def test_refresh_prices_fetches_eur_position(keyed):
    s = FakeSession([
        ("/search", _search("ISL.DE", "Common Stock")),
        ("/quote", {"c": 42.0}),
        ("/stock/profile2", {"currency": "EUR"}),
    ])
    result = refresh_prices([{"isin": "US1", "name": "ISLA"}], {}, {}, s)
    assert result["prices"]["US1"]["price"] == 42.0
    assert result["prices"]["US1"]["source"] == "finnhub"
    assert result["tickers"]["US1"] == "ISL.DE"
    assert result["skipped"] == []


def test_refresh_prices_uses_ticker_cache_without_search(keyed):
    s = FakeSession([
        ("/quote", {"c": 10.0}),
        ("/stock/profile2", {"currency": "EUR"}),
    ])
    result = refresh_prices([{"isin": "US1", "name": "ISLA"}], {}, {"US1": "AAPL"}, s)
    search_calls = [u for u, _ in s.calls if "/search" in u]
    assert search_calls == []
    assert result["tickers"]["US1"] == "AAPL"


def test_refresh_prices_skips_manual_existing(keyed):
    s = FakeSession([
        ("/search", _search("AAPL", "Common Stock")),
        ("/quote", {"c": 10.0}),
        ("/stock/profile2", {"currency": "EUR"}),
    ])
    result = refresh_prices([{"isin": "US1", "name": "ISLA"}], {"US1": {"price": 99.0, "source": "manual"}}, {}, s)
    assert "US1" not in result["prices"]
    assert result["skipped"][0]["reason"] == "manual"


def test_refresh_prices_skips_missing_ticker(keyed):
    s = FakeSession([("/search", {"count": 0, "result": []})])
    result = refresh_prices([{"isin": "US1", "name": "ISLA"}], {}, {}, s)
    assert "US1" not in result["prices"]
    assert result["skipped"][0]["reason"] == "no_ticker"


def test_to_eur_converts_non_eur_currency():
    s = FakeSession([("/v1/latest", {"rates": {"EUR": 1.1}})])
    assert to_eur(10.0, "GBP", s) == pytest.approx(11.0)
    assert to_eur(10.0, "EUR", s) == 10.0


def test_refresh_prices_converts_fx_to_eur(keyed):
    s = FakeSession([
        ("/search", _search("CSPX.L", "ETP")),
        ("/quote", {"c": 20.0}),
        ("/stock/profile2", {"currency": "GBP"}),
        ("/v1/latest", {"rates": {"EUR": 1.2}}),
    ])
    result = refresh_prices([{"isin": "US1", "name": "CSPX"}], {}, {}, s)
    assert result["prices"]["US1"]["price"] == pytest.approx(24.0)


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

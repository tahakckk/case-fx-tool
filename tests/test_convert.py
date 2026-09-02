from decimal import Decimal
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


TODAY = date(2026, 8, 31)


def create_test_app(transport):
    return create_app(transport, today=lambda: TODAY)


@pytest.fixture(autouse=True)
def block_real_http(monkeypatch):
    monkeypatch.setenv("FX_UPSTREAM_BASE", "https://upstream.invalid/fx/")
    def blocked(*args, **kwargs):
        pytest.fail("Unexpected real HTTP call: tests must use MockTransport")

    async def async_blocked(*args, **kwargs):
        blocked()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)


def strict_transport(handler, expected_dates):
    pending = iter(expected_dates)

    def respond(request):
        expected_date = next(pending, None)
        assert expected_date is not None, f"Unexpected extra upstream call: {request.url}"
        assert request.method == "GET"
        assert str(request.url) == (
            f"https://upstream.invalid/fx/v1/{expected_date}?base=EUR&symbols=TRY"
        ), f"Unexpected upstream URL: {request.url}"
        return handler(request)

    return httpx.MockTransport(respond)


@pytest.fixture
def fake_api(request):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            text='{"base":"EUR","date":"2026-08-28","rates":{"TRY":47.1234}}',
        )

    expected_dates = getattr(request, "param", ["2026-08-30"])
    with TestClient(create_test_app(strict_transport(respond, expected_dates))) as client:
        yield client, calls


def query(**overrides):
    return {"amount": "250", "from": "EUR", "to": "TRY", "date": "2026-08-30", **overrides}


def test_success_uses_actual_rate_date_and_configured_upstream(fake_api):
    client, calls = fake_api
    response = client.get("/tools/convert", params=query())
    assert response.status_code == 200
    assert response.json() == {
        "amount": 250,
        "from": "EUR",
        "to": "TRY",
        "rate": 47.1234,
        "result": 11780.85,
        "rate_date": "2026-08-28",
        "asked_date": "2026-08-30",
        "source": "ECB via frankfurter.dev",
    }
    assert len(calls) == 1
    assert str(calls[0].url) == (
        "https://upstream.invalid/fx/v1/2026-08-30?base=EUR&symbols=TRY"
    )


def test_cache_reuses_rate_for_normalized_pair_and_different_amount(fake_api):
    client, calls = fake_api
    first = client.get("/tools/convert", params=query())
    second = client.get(
        "/tools/convert", params=query(amount="2", **{"from": " eur ", "to": "try"})
    )
    assert first.status_code == second.status_code == 200
    assert len(calls) == 1
    assert second.json()["amount"] == 2
    assert second.json()["result"] == 94.25
    assert second.json()["rate"] == first.json()["rate"]
    assert second.json()["rate_date"] == "2026-08-28"
    assert second.json()["asked_date"] == "2026-08-30"


@pytest.mark.parametrize("fake_api", [["2026-08-30", "2026-08-31"]], indirect=True)
def test_different_asked_date_fetches_separately(fake_api):
    client, calls = fake_api
    for day in ("2026-08-30", "2026-08-31"):
        response = client.get("/tools/convert", params=query(date=day))
        assert response.status_code == 200
        assert response.json()["asked_date"] == day
    assert [request.url.path for request in calls] == [
        "/fx/v1/2026-08-30", "/fx/v1/2026-08-31"
    ]


def test_decimal_rounding_is_half_up():
    def respond(request):
        return httpx.Response(
            200, text='{"base":"EUR","date":"2026-08-28","rates":{"TRY":1.005}}'
        )

    with TestClient(create_test_app(strict_transport(respond, ["2026-08-30"]))) as client:
        response = client.get("/tools/convert", params=query(amount="1"))
    assert response.status_code == 200
    assert Decimal(str(response.json()["result"])) == Decimal("1.01")


@pytest.mark.parametrize("missing", ["amount", "from", "to", "date"])
def test_all_query_parameters_are_required(fake_api, missing):
    client, calls = fake_api
    params = query()
    del params[missing]
    response = client.get("/tools/convert", params=params)
    assert response.status_code == 422
    assert set(response.json()) == {"error", "message"}
    expected = {"amount": "invalid_amount", "from": "invalid_currency", "to": "invalid_currency", "date": "invalid_date"}
    assert response.json()["error"] == expected[missing]
    assert calls == []
    assert client.app.state.fx_service.cache == {}


def test_upstream_failure_is_not_a_successful_zero():
    transport = strict_transport(lambda request: httpx.Response(500), ["2026-08-30"])
    with TestClient(create_test_app(transport)) as client:
        response = client.get("/tools/convert", params=query())
    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"amount": "not-a-number"}, "invalid_amount"),
        ({"amount": ""}, "invalid_amount"),
        ({"amount": "-1"}, "invalid_amount"),
        ({"amount": "NaN"}, "invalid_amount"),
        ({"amount": "sNaN"}, "invalid_amount"),
        ({"amount": "Infinity"}, "invalid_amount"),
        ({"amount": "-Infinity"}, "invalid_amount"),
        ({"amount": "0.12345678901"}, "invalid_amount"),
        ({"amount": "1.00000000000"}, "invalid_amount"),
        ({"amount": "1e-11"}, "invalid_amount"),
        ({"from": "EU"}, "invalid_currency"),
        ({"to": "TRYY"}, "invalid_currency"),
        ({"from": "E1R"}, "invalid_currency"),
        ({"to": "TR1"}, "invalid_currency"),
        ({"from": "ÉUR"}, "invalid_currency"),
        ({"to": "trı"}, "invalid_currency"),
        ({"from": "ßa"}, "invalid_currency"),
        ({"from": ""}, "invalid_currency"),
        ({"to": "   "}, "invalid_currency"),
        ({"from": "E R"}, "invalid_currency"),
        ({"from": " eur ", "to": "EUR"}, "same_currency"),
        ({"date": ""}, "invalid_date"),
        ({"date": "2026/08/30"}, "invalid_date"),
        ({"date": "2026-8-30"}, "invalid_date"),
        ({"date": "20260830"}, "invalid_date"),
        ({"date": "2026-08-30T00:00:00"}, "invalid_date"),
        ({"date": " 2026-08-30 "}, "invalid_date"),
        ({"date": "2026-02-30"}, "invalid_date"),
        ({"date": "0000-01-01"}, "invalid_date"),
        ({"date": "2026-09-01"}, "future_date"),
        ({"amount": "bad", "from": "bad!", "date": "bad"}, "invalid_amount"),
        ({"from": "bad!", "date": "bad"}, "invalid_currency"),
        ({"to": "EUR", "date": "bad"}, "same_currency"),
    ],
)
def test_invalid_input_has_no_upstream_or_cache_effect(fake_api, changes, code):
    client, calls = fake_api
    cache_before = client.app.state.fx_service.cache.copy()
    response = client.get("/tools/convert", params=query(**changes))
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error", "message"}
    assert body["error"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert calls == []
    assert client.app.state.fx_service.cache == cache_before


@pytest.mark.parametrize(
    "amount,expected_result",
    [("0", 0), ("0.1234567890", 5.82), ("1e-10", 0), ("1e2", 4712.34)],
)
def test_valid_amount_precision(fake_api, amount, expected_result):
    client, calls = fake_api
    response = client.get("/tools/convert", params=query(amount=amount))
    assert response.status_code == 200
    assert response.json()["amount"] == float(Decimal(amount))
    assert response.json()["result"] == expected_result
    assert len(calls) == 1


def test_normalization_before_first_upstream_call(fake_api):
    client, calls = fake_api
    response = client.get(
        "/tools/convert", params=query(**{"from": " eur ", "to": " try "})
    )
    assert response.status_code == 200
    assert response.json()["from"] == "EUR"
    assert response.json()["to"] == "TRY"
    assert len(calls) == 1


@pytest.mark.parametrize("fake_api", [["2026-08-31"]], indirect=True)
def test_today_is_allowed(fake_api):
    client, calls = fake_api
    response = client.get("/tools/convert", params=query(date=TODAY.isoformat()))
    assert response.status_code == 200
    assert response.json()["asked_date"] == "2026-08-31"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "params,code",
    [({}, "invalid_amount"), ({"amount": "1"}, "invalid_currency"),
     ({"amount": "1", "from": "EUR", "to": "TRY"}, "invalid_date")],
)
def test_multiple_missing_parameters_have_deterministic_error(fake_api, params, code):
    client, calls = fake_api
    response = client.get("/tools/convert", params=params)
    assert response.status_code == 422
    assert set(response.json()) == {"error", "message"}
    assert response.json()["error"] == code
    assert calls == []
    assert client.app.state.fx_service.cache == {}


def test_invalid_amount_cannot_use_or_mutate_existing_cache(fake_api):
    client, calls = fake_api
    assert client.get("/tools/convert", params=query()).status_code == 200
    cache_before = client.app.state.fx_service.cache.copy()
    response = client.get("/tools/convert", params=query(amount="-1"))
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_amount"
    assert set(response.json()) == {"error", "message"}
    assert len(calls) == 1
    assert client.app.state.fx_service.cache == cache_before


@pytest.mark.parametrize("method,path,status", [("GET", "/missing", 404), ("POST", "/tools/convert", 405)])
def test_framework_errors_use_common_body(fake_api, method, path, status):
    client, calls = fake_api
    response = client.request(method, path)
    assert response.status_code == status
    assert set(response.json()) == {"error", "message"}
    assert response.json()["error"] == "http_error"
    assert calls == []

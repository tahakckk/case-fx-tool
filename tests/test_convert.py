from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


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
    with TestClient(create_app(strict_transport(respond, expected_dates))) as client:
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

    with TestClient(create_app(strict_transport(respond, ["2026-08-30"]))) as client:
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
    assert calls == []


def test_upstream_failure_is_not_a_successful_zero():
    transport = strict_transport(lambda request: httpx.Response(500), ["2026-08-30"])
    with TestClient(create_app(transport)) as client:
        response = client.get("/tools/convert", params=query())
    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"

# FX Conversion Tool

A FastAPI currency conversion service callable by an AI agent, using ECB via frankfurter.dev. The actual publication date of the rate used is always shown in `rate_date`.

## Requirements and setup

Tested with Python 3.12. Use Bash for the shell scripts and keep the virtual environment active.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

```bash
./run.sh
```

The default port is 8080. To use another port:

```bash
PORT=8090 ./run.sh
```

`FX_UPSTREAM_BASE` defaults to `https://api.frankfurter.dev`; override it to point at a fake upstream. Requests use `/v1/{date}` with `base` and `symbols` query parameters.

## Example request

`GET /tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28`

```bash
curl "http://127.0.0.1:8080/tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28"
```

Success returns HTTP 200. These numbers are illustrative, not a current quote:

```json
{
  "amount": 250,
  "from": "EUR",
  "to": "TRY",
  "rate": 47.1234,
  "result": 11780.85,
  "rate_date": "2026-08-28",
  "asked_date": "2026-08-28",
  "source": "ECB via frankfurter.dev"
}
```

## Test

After installing dependencies, run:

```bash
./test.sh
FX_UPSTREAM_BASE=http://127.0.0.1:1 ./test.sh
```

Tests use a fake upstream through `httpx.MockTransport` and a fixed clock. They use no real network and fail on unexpected HTTP calls. `test.sh` does not install dependencies.

## Input and date policies

| Input or case | Behavior |
|---|---|
| `amount` | Required and numeric; zero accepted; negative values, NaN and Infinity rejected. |
| Amount precision | At most 10 decimal places, including trailing zeros; excess precision is rejected, not rounded. |
| `from`, `to` | Required; trim surrounding whitespace, require exactly three ASCII letters, then uppercase. No supported-currency list is hardcoded. |
| Same currency | Rejected after normalization. |
| `date` | Required, valid `YYYY-MM-DD`; future dates are rejected against the system's current local date. |
| Weekend or holiday | Accept an earlier publication date returned by the dated upstream endpoint; no `/latest` fallback. |
| Date labels | `asked_date` is the requested date; `rate_date` is the upstream publication date, even when earlier. Equal dates are accepted; later rate dates are rejected. |
| No available rate / before the series | Return an error when the upstream reports no rate; never invent one or substitute a later rate. |

Calculations use `Decimal` without rounding the rate first. The result is rounded to two decimal places with `ROUND_HALF_UP`. Upstream rates must be positive, finite JSON numbers; numeric strings are rejected.

## Error responses

Errors use a non-2xx status and this body, without upstream diagnostics:

```json
{"error": "<short_machine_code>", "message": "<human-readable sentence>"}
```

| Code | HTTP | Condition |
|---|---:|---|
| `invalid_amount` | 422 | Missing, unparseable, negative, non-finite or over-precision amount. |
| `invalid_currency` | 422 | Missing currency or invalid three-ASCII-letter format. |
| `same_currency` | 422 | Normalized source and target are equal. |
| `invalid_date` | 422 | Missing, malformed or nonexistent calendar date. |
| `future_date` | 422 | Requested date is after today. |
| `rate_unavailable` | 422 | Upstream 400/404/422, or target absent from an otherwise validated payload. |
| `upstream_timeout` | 504 | Upstream request timed out. |
| `upstream_unavailable` | 502 | Connection/transport error, upstream 429 or 5xx. |
| `invalid_upstream_response` | 502 | Other unexpected status/redirect, invalid JSON/schema/base/rate, or invalid/later rate date. |
| `invalid_request` | 422 | Framework request-validation fallback. |
| `http_error` | Original HTTP status | Framework HTTP error, such as 404 or 405. |

Input errors have a fixed priority: amount, source format, target format, same currency, date format, future date. Input validation runs before upstream access or cache changes.

## Cache behavior

The cache is an in-process dictionary keyed by normalized source, target and asked date. It stores only the validated rate and actual rate date; amount is not part of the key. Successful repeated queries reuse the rate. Errors are not cached, and restarting loses the cache. There is currently no size limit, TTL or concurrent-request coalescing.

## Structure

- `app/main.py`: FastAPI endpoint, input validation and HTTP error handlers.
- `app/config.py`: upstream base URL configuration.
- `app/models.py`: success and error response models.
- `app/fx_service.py`: upstream requests, response validation, conversion and cache.
- `tests/test_convert.py`: offline tests.
- `tool.py` and `REVIEW.md`: Part B review material.

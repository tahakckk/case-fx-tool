# Review of tool.py

Findings are ordered by customer impact.

## 1. The published query contract is silently ignored

**Affected code: lines 48-49 and 62-69.** The route expects `from_` and `on`, without aliases for `from` and `date`; those published parameters are silently ignored as extra query parameters. A brief-format `from=USD&date=2026-08-28` request uses `/v1/latest?base=EUR&symbols=TRY`. Even with a healthy upstream, the customer receives a successful calculation for the wrong currency and date. `asked_date` is also absent.

**Verification:** MockTransport captured that outgoing URL and `from: EUR` in the response to the dated USD request.

## 2. Cached rates lose their temporal identity

**Affected code: lines 28-44.** The cache stores only a rate, keyed by currency pair without a date. Upstream `date` is never read; `rate_date` comes from the request or today. One date's rate can therefore be reused and relabeled as another date's rate. When the target is missing, `/latest` fallback can even label a later publication as a historical rate.

**Verification:** Two different `on` dates produced one upstream call: the first rate was returned with the second requested date. A fake fallback published on September 1 was labeled August 30. This proves behavior for that response, not when live Frankfurter omits a target.

## 3. The upstream boundary fails open and cannot be redirected

**Affected code: lines 18, 33-43 and 71-80.** HTTP status is unchecked. Timeout, connection errors and invalid JSON become HTTP 200 with `rate: 0` and `result: 0`; a 500 containing rates can be accepted and cached. An agent may present these as monetary facts instead of invoking error/retry handling. The hardcoded host ignores `FX_UPSTREAM_BASE`, preventing controlled fake-upstream routing and operational endpoint changes through configuration.

**Verification:** MockTransport probes covered timeout, connection error, invalid JSON, 500 with/without rates and an environment override; captured requests still targeted the hardcoded host.

## 4. The rate is rounded before multiplication

**Affected code: lines 60-61.** Rounding the rate to two places before multiplication changes the customer's result: `250 × 47.1234 = 11780.85`, but using `47.12` produces `11780.00`. The discrepancy grows with amount.

**Verification:** The endpoint result from a fake upstream rate was compared with a full-precision Decimal calculation.

## The one I would fix before shipping tonight

Finding 1: the published query contract. Every historical or non-EUR brief-format request can succeed using incorrect inputs without an upstream outage. Addressing this alone would not make the service production-ready; findings 2 and 3 remain shipping blockers.

## Things that look suspicious but are fine

- Omitting amount from the cache key is valid for a unit rate. The missing pieces are the requested date and stored publication date.
- A shared `AsyncClient` supports connection pooling. It remained open after shutdown in the probe, but customer interruption or socket leakage was not demonstrated.
- The installed httpx version has a default timeout. The defect is converting timeout into false success, not an absence of timeouts.

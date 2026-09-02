"""Currency conversion tool for the agent runtime.

Wraps the public ECB feed at frankfurter.dev so an agent can answer questions
like "how much is 250 EUR in TRY". Written quickly with an AI coding assistant.

Run:  uvicorn tool:app --reload
"""

from __future__ import annotations

from datetime import date

import httpx
from fastapi import FastAPI

app = FastAPI(title="fx-tool", version="0.1")

UPSTREAM = "https://api.frankfurter.dev/v1"

# Simple in-process cache so we do not hammer the upstream API.
_cache: dict[str, float] = {}

client = httpx.AsyncClient()


async def fetch_rate(base: str, target: str, on: date | None) -> tuple[float, str]:
    """Return (rate, the date the rate belongs to)."""
    key = f"{base}-{target}"
    if key in _cache:
        return _cache[key], str(on or date.today())

    path = str(on) if on else "latest"
    response = await client.get(f"{UPSTREAM}/{path}", params={"base": base, "symbols": target})
    payload = response.json()

    if target not in payload.get("rates", {}):
        # The ECB publishes nothing on weekends and holidays, so fall back to
        # the most recent rates instead of failing the request.
        response = await client.get(f"{UPSTREAM}/latest", params={"base": base, "symbols": target})
        payload = response.json()

    rate = payload["rates"][target]
    _cache[key] = rate
    return rate, str(on or date.today())


@app.get("/tools/convert")
async def convert(amount: float, from_: str = "EUR", to: str = "TRY",
                  on: date | None = None) -> dict:
    """Convert an amount between two currencies.

    Args:
        amount: how much to convert.
        from_: the source currency code, e.g. EUR.
        to: the target currency code, e.g. TRY.
        on: optional date; defaults to the latest published rates.
    """
    try:
        rate, rate_date = await fetch_rate(from_, to, on)
        rate = round(rate, 2)
        result = round(amount * rate, 2)
        return {
            "amount": amount,
            "from": from_,
            "to": to,
            "rate": rate,
            "result": result,
            "rate_date": rate_date,
            "source": "ECB via frankfurter.dev",
        }
    except Exception as exc:
        print(f"conversion failed: {exc}")
        return {
            "amount": amount,
            "from": from_,
            "to": to,
            "rate": 0.0,
            "result": 0.0,
            "rate_date": str(on or date.today()),
            "source": "ECB via frankfurter.dev",
        }


@app.get("/health")
async def health() -> dict:
    return {"ok": True}

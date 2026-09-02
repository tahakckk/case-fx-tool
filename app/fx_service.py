import json
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext

import httpx

from app.models import ConversionResponse


class UpstreamError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.status, self.message = {
            "rate_unavailable": (422, "No rate is available for the requested currencies and date."),
            "upstream_timeout": (504, "The rate provider timed out."),
            "upstream_unavailable": (502, "The rate provider is unavailable."),
            "invalid_upstream_response": (502, "The rate provider returned an invalid response."),
        }[code]
        super().__init__(self.message)


def validate_payload(content: bytes, base: str, target: str, asked_date: date) -> tuple[Decimal, date]:
    invalid = "invalid_upstream_response"
    try:
        payload = json.loads(
            content, parse_float=Decimal, parse_int=Decimal, parse_constant=Decimal
        )
    except ValueError:
        raise UpstreamError(invalid) from None
    if not isinstance(payload, dict):
        raise UpstreamError(invalid)
    raw_base, raw_date, rates = payload.get("base"), payload.get("date"), payload.get("rates")
    if (
        not isinstance(raw_base, str)
        or re.fullmatch(r"[A-Za-z]{3}", raw_base.strip()) is None
        or raw_base.strip().upper() != base
        or not isinstance(raw_date, str)
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_date) is None
        or not isinstance(rates, dict)
    ):
        raise UpstreamError(invalid)
    try:
        rate_date = date.fromisoformat(raw_date)
    except ValueError:
        raise UpstreamError(invalid) from None
    if rate_date > asked_date:
        raise UpstreamError(invalid)
    if target not in rates:
        raise UpstreamError("rate_unavailable")
    rate = rates[target]
    if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0:
        raise UpstreamError(invalid)
    return rate, rate_date


class FXService:
    def __init__(self, client: httpx.AsyncClient, upstream_base: str):
        self.client = client
        self.upstream_base = upstream_base
        self.cache: dict[tuple[str, str, date], tuple[Decimal, date]] = {}

    async def convert(
        self, amount: Decimal, base: str, target: str, asked_date: date
    ) -> ConversionResponse:
        base, target = base.strip().upper(), target.strip().upper()
        key = (base, target, asked_date)
        if key not in self.cache:
            try:
                response = await self.client.get(
                    f"{self.upstream_base}/v1/{asked_date.isoformat()}",
                    params={"base": base, "symbols": target},
                    follow_redirects=False,
                )
            except httpx.TimeoutException:
                raise UpstreamError("upstream_timeout") from None
            except httpx.RequestError:
                raise UpstreamError("upstream_unavailable") from None
            if response.status_code in (400, 404, 422):
                raise UpstreamError("rate_unavailable")
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                raise UpstreamError("upstream_unavailable")
            if not 200 <= response.status_code <= 299:
                raise UpstreamError("invalid_upstream_response")
            self.cache[key] = validate_payload(response.content, base, target, asked_date)

        rate, rate_date = self.cache[key]
        with localcontext() as context:
            context.prec = max(
                28,
                len(amount.as_tuple().digits) + len(rate.as_tuple().digits),
                amount.adjusted() + rate.adjusted() + 5,
            )
            result = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return ConversionResponse(
            amount=amount,
            from_currency=base,
            to=target,
            rate=rate,
            result=result,
            rate_date=rate_date,
            asked_date=asked_date,
        )

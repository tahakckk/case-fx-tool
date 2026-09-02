import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext

import httpx
from pydantic import BaseModel, ValidationError

from app.models import ConversionResponse


class UpstreamError(Exception):
    pass


class RatePayload(BaseModel):
    base: str
    date: date
    rates: dict[str, Decimal]


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
                )
                response.raise_for_status()
                payload = RatePayload.model_validate(
                    json.loads(response.content, parse_float=Decimal)
                )
                rate = payload.rates[target]
                if (
                    payload.base != base
                    or payload.date > asked_date
                    or not rate.is_finite()
                    or rate <= 0
                ):
                    raise ValueError("Invalid upstream rate or date")
            except (httpx.HTTPError, ValueError, KeyError, ValidationError) as exc:
                raise UpstreamError("Could not obtain a valid upstream rate.") from exc
            self.cache[key] = (rate, payload.date)

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

from contextlib import asynccontextmanager
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Annotated

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.config import upstream_base
from app.fx_service import FXService, UpstreamError
from app.models import ConversionResponse, ErrorResponse


class InvalidInput(Exception):
    def __init__(self, code: str, message: str):
        self.error = ErrorResponse(error=code, message=message)


def validate_amount(raw: str | None) -> Decimal:
    message = "Amount must be a finite non-negative number with at most 10 decimal places."
    try:
        value = Decimal(raw) if raw is not None else Decimal("NaN")
    except InvalidOperation:
        raise InvalidInput("invalid_amount", message) from None
    if not value.is_finite() or value < 0:
        raise InvalidInput("invalid_amount", message)
    if max(0, -value.as_tuple().exponent) > 10:
        raise InvalidInput("invalid_amount", message)
    return value


def validate_currency(raw: str | None) -> str:
    value = raw.strip() if raw is not None else ""
    if re.fullmatch(r"[A-Za-z]{3}", value) is None:
        raise InvalidInput("invalid_currency", "Currencies must contain exactly three ASCII letters.")
    return value.upper()


def validate_date(raw: str | None, today: Callable[[], date]) -> date:
    message = "Date must be a valid calendar date in YYYY-MM-DD format."
    if raw is None or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw) is None:
        raise InvalidInput("invalid_date", message)
    try:
        value = date.fromisoformat(raw)
    except ValueError:
        raise InvalidInput("invalid_date", message) from None
    if value > today():
        raise InvalidInput("future_date", "Date must not be in the future.")
    return value


def create_app(
    transport: httpx.AsyncBaseTransport | None = None,
    today: Callable[[], date] = date.today,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        async with httpx.AsyncClient(transport=transport, timeout=5.0) as client:
            application.state.fx_service = FXService(client, upstream_base())
            yield

    application = FastAPI(
        lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )

    @application.exception_handler(InvalidInput)
    async def invalid_input(request: Request, exc: InvalidInput) -> JSONResponse:
        return JSONResponse(status_code=422, content=exc.error.model_dump())

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        error = ErrorResponse(error="http_error", message="The HTTP request could not be handled.")
        return JSONResponse(status_code=exc.status_code, content=error.model_dump(), headers=exc.headers)

    @application.exception_handler(UpstreamError)
    async def upstream_error(request: Request, exc: UpstreamError) -> JSONResponse:
        error = ErrorResponse(error="upstream_error", message=str(exc))
        return JSONResponse(status_code=502, content=error.model_dump())

    @application.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        error = ErrorResponse(
            error="invalid_request", message="Provide valid amount, from, to and date parameters."
        )
        return JSONResponse(status_code=422, content=error.model_dump())

    @application.get("/tools/convert", response_model=ConversionResponse)
    async def convert(
        request: Request,
        amount: Annotated[str | None, Query()] = None,
        from_currency: Annotated[str | None, Query(alias="from")] = None,
        to: Annotated[str | None, Query()] = None,
        asked_date: Annotated[str | None, Query(alias="date")] = None,
    ) -> ConversionResponse:
        # Validate in a fixed order before touching the service or its cache.
        valid_amount = validate_amount(amount)
        base = validate_currency(from_currency)
        target = validate_currency(to)
        if base == target:
            raise InvalidInput("same_currency", "Source and target currencies must differ.")
        valid_date = validate_date(asked_date, today)
        return await request.app.state.fx_service.convert(
            valid_amount, base, target, valid_date
        )

    return application


app = create_app()

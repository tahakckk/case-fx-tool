from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Annotated

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import upstream_base
from app.fx_service import FXService, UpstreamError
from app.models import ConversionResponse, ErrorResponse


def create_app(transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        async with httpx.AsyncClient(transport=transport, timeout=5.0) as client:
            application.state.fx_service = FXService(client, upstream_base())
            yield

    application = FastAPI(
        lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )

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
        amount: Annotated[Decimal, Query(allow_inf_nan=False)],
        from_currency: Annotated[str, Query(alias="from")],
        to: Annotated[str, Query()],
        asked_date: Annotated[date, Query(alias="date")],
    ) -> ConversionResponse:
        return await request.app.state.fx_service.convert(
            amount, from_currency, to, asked_date
        )

    return application


app = create_app()

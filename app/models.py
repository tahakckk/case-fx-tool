from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer


class ConversionResponse(BaseModel):
    amount: Decimal
    from_currency: str = Field(serialization_alias="from")
    to: str
    rate: Decimal
    result: Decimal
    rate_date: date
    asked_date: date
    source: str = "ECB via frankfurter.dev"

    @field_serializer("amount", "rate", "result", when_used="json")
    def serialize_number(self, value: Decimal) -> float:
        # The HTTP contract uses JSON numbers, rather than decimal strings.
        return float(value)


class ErrorResponse(BaseModel):
    error: str
    message: str

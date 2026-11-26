from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LotteryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    start_number: int = Field(ge=0)
    end_number: int = Field(ge=0)
    ticket_price: Decimal = Field(default=Decimal("100.00"), ge=0)
    currency: str = Field(default="ETB", min_length=1, max_length=10)
    reservation_duration_hours: int = Field(default=24, ge=1)
    max_numbers_per_customer: int = Field(default=100, ge=1)
    status: str = Field(default="DRAFT")

    @field_validator("end_number")
    @classmethod
    def end_must_not_precede_start(cls, value: int, info) -> int:
        start = info.data.get("start_number")
        if start is not None and value < start:
            raise ValueError("end_number must be greater than or equal to start_number")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DRAFT", "ACTIVE", "PAUSED", "CLOSED"}:
            raise ValueError("status must be DRAFT, ACTIVE, PAUSED, or CLOSED")
        return value


class LotteryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    start_number: int | None = Field(default=None, ge=0)
    end_number: int | None = Field(default=None, ge=0)
    ticket_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=1, max_length=10)
    reservation_duration_hours: int | None = Field(default=None, ge=1)
    max_numbers_per_customer: int | None = Field(default=None, ge=1)
    status: str | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.upper()
        if value not in {"DRAFT", "ACTIVE", "PAUSED", "CLOSED"}:
            raise ValueError("status must be DRAFT, ACTIVE, PAUSED, or CLOSED")
        return value


class LotteryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    start_number: int
    end_number: int
    ticket_price: Decimal
    currency: str
    reservation_duration_hours: int
    max_numbers_per_customer: int
    status: str
    created_at: datetime


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    status: str


class TicketPageResponse(BaseModel):
    items: list[TicketResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ManagedTicketResponse(TicketResponse):
    customer_name: str | None
    phone_number: str | None


class ManagedTicketPageResponse(BaseModel):
    items: list[ManagedTicketResponse]
    total: int
    page: int
    page_size: int
    pages: int

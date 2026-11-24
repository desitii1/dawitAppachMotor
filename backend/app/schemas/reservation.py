from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReservationCreate(BaseModel):
    telegram_id: int = Field(gt=0)
    telegram_username: str | None = None
    full_name: str = Field(min_length=1, max_length=255)
    phone_number: str = Field(min_length=9, max_length=32)
    lottery_id: int = Field(gt=0)
    numbers: list[str] = Field(min_length=1)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("full_name cannot be blank")
        return value

    @field_validator("numbers")
    @classmethod
    def validate_numbers(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not normalized:
            raise ValueError("At least one number is required")
        return normalized


class ReservationItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: str


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    customer_id: int
    lottery_id: int
    status: str
    total_amount: Decimal
    expires_at: datetime
    created_at: datetime


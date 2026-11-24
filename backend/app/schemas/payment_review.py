from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PaymentApproveRequest(BaseModel):
    allow_expired_explicit: bool = False


class PaymentRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=1000)


class PaymentReviewResponse(BaseModel):
    payment_id: int
    reservation_reference: str
    status: str
    amount: Decimal
    approved_at: datetime | None = None
    rejection_reason: str | None = None

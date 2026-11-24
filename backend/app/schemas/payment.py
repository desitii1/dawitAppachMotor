from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PaymentAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    storage_key: str
    original_filename: str | None
    uploaded_at: datetime


class PaymentSubmissionResponse(BaseModel):
    payment_id: int
    reservation_reference: str
    status: str
    amount: Decimal
    attachment: PaymentAttachmentResponse

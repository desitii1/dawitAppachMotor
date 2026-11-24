from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.payment import PaymentSubmissionResponse
from app.services.payment_service import (
    PaymentSubmissionError,
    submit_payment_screenshot,
)


router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/reservations/{reservation_reference}/screenshots",
    response_model=PaymentSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_screenshot(
    reservation_reference: str,
    telegram_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    try:
        payment, attachment = submit_payment_screenshot(
            db,
            reservation_reference=reservation_reference,
            telegram_id=telegram_id,
            content=content,
            content_type=file.content_type or "application/octet-stream",
            original_filename=file.filename or "payment-screenshot",
            attachment_root=settings.attachment_root,
        )
    except PaymentSubmissionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return {
        "payment_id": payment.id,
        "reservation_reference": reservation_reference,
        "status": payment.status,
        "amount": payment.amount,
        "attachment": attachment,
    }

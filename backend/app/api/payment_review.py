from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.admin import AdminUser
from app.models.payment import Payment, PaymentAttachment
from app.models.reservation import Reservation
from app.models.customer import Customer
from app.models.reservation import ReservationItem
from app.models.ticket import Ticket
from app.schemas.payment_review import (
    PaymentApproveRequest,
    PaymentRejectRequest,
    PaymentReviewResponse,
)
from app.security.authentication import get_current_admin
from app.services.payment_service import (
    PaymentReviewError,
    approve_payment,
    reject_payment,
)


router = APIRouter(prefix="/admin/payments", tags=["payment-review"])


@router.get("/pending")
def list_pending(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    payments = db.scalars(
        select(Payment)
        .where(Payment.status == "PAYMENT_SUBMITTED")
        .order_by(Payment.submitted_at.desc())
    ).all()
    result = []
    for payment in payments:
        reservation = db.get(Reservation, payment.reservation_id)
        customer = db.get(Customer, payment.customer_id)
        numbers = db.scalars(
            select(Ticket.number)
            .join(ReservationItem, ReservationItem.ticket_id == Ticket.id)
            .where(ReservationItem.reservation_id == payment.reservation_id)
            .order_by(Ticket.number)
        ).all()
        attachment = db.scalar(
            select(PaymentAttachment).where(PaymentAttachment.payment_id == payment.id)
        )
        result.append({
            "payment_id": payment.id,
            "reservation_reference": reservation.reference if reservation else None,
            "customer_name": customer.full_name if customer else None,
            "phone_number": customer.phone_number if customer else None,
            "telegram_id": customer.telegram_id if customer else None,
            "numbers": list(numbers),
            "amount": payment.amount,
            "status": payment.status,
            "submitted_at": payment.submitted_at,
            "expires_at": reservation.expires_at if reservation else None,
            "has_attachment": attachment is not None,
        })
    return result


@router.post("/{payment_id}/approve", response_model=PaymentReviewResponse)
def approve(
    payment_id: int,
    payload: PaymentApproveRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    try:
        payment, reservation = approve_payment(
            db,
            payment_id=payment_id,
            admin=admin,
            allow_expired_explicit=payload.allow_expired_explicit,
        )
    except PaymentReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "payment_id": payment.id,
        "reservation_reference": reservation.reference,
        "status": payment.status,
        "amount": payment.amount,
        "approved_at": payment.approved_at,
        "rejection_reason": payment.rejection_reason,
    }


@router.post("/{payment_id}/reject", response_model=PaymentReviewResponse)
def reject(
    payment_id: int,
    payload: PaymentRejectRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    try:
        payment, reservation = reject_payment(
            db,
            payment_id=payment_id,
            admin=admin,
            rejection_reason=payload.rejection_reason,
        )
    except PaymentReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "payment_id": payment.id,
        "reservation_reference": reservation.reference,
        "status": payment.status,
        "amount": payment.amount,
        "approved_at": payment.approved_at,
        "rejection_reason": payment.rejection_reason,
    }


@router.get("/{payment_id}/attachment")
def get_attachment(
    payment_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    attachment = db.scalar(
        select(PaymentAttachment).where(PaymentAttachment.payment_id == payment_id)
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Payment attachment not found")
    path = (Path(settings.attachment_root).resolve() / attachment.storage_key).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Payment attachment file not found")
    return FileResponse(path, filename=attachment.original_filename)

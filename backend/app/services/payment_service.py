from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.payment import Payment, PaymentAttachment
from app.models.reservation import Reservation
from app.models.reservation import ReservationItem
from app.models.ticket import Ticket
from app.models.activity import ActivityLog
from app.models.admin import AdminUser
from app.models.customer import Customer
import asyncio
import logging
from aiogram import Bot
from app.config import settings


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class PaymentSubmissionError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def submit_payment_screenshot(
    db: Session,
    *,
    reservation_reference: str,
    telegram_id: int,
    content: bytes,
    content_type: str,
    original_filename: str,
    attachment_root: str,
    replace_existing: bool = False,
) -> tuple[Payment, PaymentAttachment]:
    if content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise PaymentSubmissionError("Only JPEG, PNG, and WebP screenshots are allowed")
    if len(content) == 0:
        raise PaymentSubmissionError("The payment screenshot is empty")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise PaymentSubmissionError("The payment screenshot exceeds 10 MB")

    customer = db.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
    if customer is None:
        raise PaymentSubmissionError("Customer not found", 404)

    reservation = db.scalar(
        select(Reservation).where(
            Reservation.reference == reservation_reference,
            Reservation.customer_id == customer.id,
        )
    )
    if reservation is None:
        raise PaymentSubmissionError("Reservation not found", 404)
    if reservation.status not in {"AWAITING_PAYMENT", "PAYMENT_SUBMITTED"}:
        raise PaymentSubmissionError("Payment screenshots cannot be submitted for this reservation")
    expires_at = reservation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise PaymentSubmissionError("This reservation has expired")

    payment = db.scalar(select(Payment).where(Payment.reservation_id == reservation.id))
    if payment is None:
        raise PaymentSubmissionError("Payment record not found", 404)
    if payment.status in {"APPROVED", "REJECTED", "EXPIRED"}:
        raise PaymentSubmissionError("Payment status no longer allows a screenshot submission")

    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }[content_type]
    root = Path(attachment_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    storage_key = f"payments/{reservation.id}/{uuid4().hex}{extension}"
    destination = (root / storage_key).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)

    attachment = PaymentAttachment(
        payment_id=payment.id,
        storage_key=storage_key,
        original_filename=original_filename[:255],
    )
    old_attachments = (
        db.scalars(
            select(PaymentAttachment).where(PaymentAttachment.payment_id == payment.id)
        ).all()
        if replace_existing
        else []
    )
    old_storage_keys = [old_attachment.storage_key for old_attachment in old_attachments]
    payment.status = "PAYMENT_SUBMITTED"
    payment.submitted_at = datetime.now(timezone.utc)
    reservation.status = "PAYMENT_SUBMITTED"
    numbers = db.scalars(
        select(Ticket.number)
        .join(ReservationItem, ReservationItem.ticket_id == Ticket.id)
        .where(ReservationItem.reservation_id == reservation.id)
        .order_by(Ticket.number)
    ).all()
    customer.last_activity_at = payment.submitted_at
    db.add(
        ActivityLog(
            customer_id=customer.id,
            activity_type=(
                "PAYMENT_SCREENSHOT_REPLACED"
                if replace_existing and old_attachments
                else "PAYMENT_SCREENSHOT_SUBMITTED"
            ),
            description=(
                f"Payment screenshot replaced for numbers {', '.join(numbers)}"
                if replace_existing and old_attachments
                else f"Payment screenshot submitted for numbers {', '.join(numbers)}"
            ),
        )
    )
    for old_attachment in old_attachments:
        db.delete(old_attachment)
    db.add(attachment)
    db.commit()
    for storage_key in old_storage_keys:
        old_path = (root / storage_key).resolve()
        if old_path.is_relative_to(root) and old_path != destination:
            try:
                old_path.unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning(
                    "Could not remove replaced payment attachment at %s",
                    old_path,
                    exc_info=True,
                )
    db.refresh(attachment)
    db.refresh(payment)
    return payment, attachment


class PaymentReviewError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _notify_customer(customer: Customer, message: str) -> None:
    if not settings.telegram_bot_token:
        return
    async def send() -> None:
        bot = Bot(token=settings.telegram_bot_token)
        try:
            await bot.send_message(customer.telegram_id, message)
        finally:
            await bot.session.close()
    try:
        asyncio.run(send())
    except RuntimeError:
        return
    except Exception:
        return


def approve_payment(
    db: Session,
    *,
    payment_id: int,
    admin: AdminUser,
    allow_expired_explicit: bool = False,
) -> tuple[Payment, Reservation]:
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise PaymentReviewError("Payment not found", 404)
    if payment.status == "APPROVED":
        raise PaymentReviewError("This payment has already been approved", 409)
    if payment.status != "PAYMENT_SUBMITTED":
        raise PaymentReviewError("Only submitted payments can be approved")

    reservation = db.scalar(
        select(Reservation)
        .where(Reservation.id == payment.reservation_id)
        .with_for_update()
    )
    if reservation is None:
        raise PaymentReviewError("Reservation not found", 404)
    if reservation.status not in {"AWAITING_PAYMENT", "PAYMENT_SUBMITTED", "EXPIRED"}:
        raise PaymentReviewError("Reservation is not in an approvable state")

    expired = reservation.expires_at <= datetime.now(timezone.utc)
    if expired and not allow_expired_explicit:
        raise PaymentReviewError(
            "This reservation has expired. Explicit expired-reservation review is required.",
            409,
        )

    ticket_ids = db.scalars(
        select(ReservationItem.ticket_id).where(
            ReservationItem.reservation_id == reservation.id
        )
    ).all()
    tickets = db.scalars(
        select(Ticket)
        .where(Ticket.id.in_(ticket_ids))
        .with_for_update()
    ).all()
    if len(tickets) != len(ticket_ids):
        raise PaymentReviewError("Reservation ticket records are incomplete")

    now = datetime.now(timezone.utc)
    for ticket in tickets:
        if ticket.status != "RESERVED" or ticket.reservation_id != reservation.id:
            raise PaymentReviewError(
                f"Ticket {ticket.number} is no longer owned by this reservation",
                409,
            )
        ticket.status = "SOLD"
        ticket.sold_at = now

    reservation.status = "APPROVED"
    payment.status = "APPROVED"
    payment.approved_at = now

    customer = db.scalar(select(Customer).where(Customer.id == payment.customer_id))
    db.add(
        ActivityLog(
            customer_id=customer.id if customer else None,
            admin_user_id=admin.id,
            activity_type="PAYMENT_APPROVED",
            description=f"Payment {payment.id} approved for numbers {', '.join(ticket.number for ticket in tickets)}",
        )
    )
    db.commit()
    db.refresh(payment)
    db.refresh(reservation)

    if customer:
        _notify_customer(
            customer,
            f"Payment approved. Your numbers {', '.join(ticket.number for ticket in tickets)} are now confirmed.",
        )
    return payment, reservation


def reject_payment(
    db: Session,
    *,
    payment_id: int,
    admin: AdminUser,
    rejection_reason: str,
) -> tuple[Payment, Reservation]:
    reason = rejection_reason.strip()
    if not reason:
        raise PaymentReviewError("A rejection reason is required")

    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise PaymentReviewError("Payment not found", 404)
    if payment.status == "REJECTED":
        raise PaymentReviewError("This payment has already been rejected", 409)
    if payment.status == "APPROVED":
        raise PaymentReviewError("An approved payment cannot be rejected", 409)

    reservation = db.scalar(
        select(Reservation)
        .where(Reservation.id == payment.reservation_id)
        .with_for_update()
    )
    if reservation is None:
        raise PaymentReviewError("Reservation not found", 404)

    ticket_ids = db.scalars(
        select(ReservationItem.ticket_id).where(
            ReservationItem.reservation_id == reservation.id
        )
    ).all()
    tickets = db.scalars(
        select(Ticket)
        .where(Ticket.id.in_(ticket_ids))
        .with_for_update()
    ).all()
    for ticket in tickets:
        if ticket.reservation_id == reservation.id:
            ticket.status = "AVAILABLE"
            ticket.reservation_id = None
            ticket.customer_id = None
            ticket.sold_at = None

    reservation.status = "REJECTED"
    payment.status = "REJECTED"
    payment.rejection_reason = reason

    customer = db.scalar(select(Customer).where(Customer.id == payment.customer_id))
    db.add(
        ActivityLog(
            customer_id=customer.id if customer else None,
            admin_user_id=admin.id,
            activity_type="PAYMENT_REJECTED",
            description=f"Payment {payment.id} rejected for numbers {', '.join(ticket.number for ticket in tickets)}: {reason}",
        )
    )
    db.commit()
    db.refresh(payment)
    db.refresh(reservation)

    if customer:
        _notify_customer(
            customer,
            f"Payment for numbers {', '.join(ticket.number for ticket in tickets)} was rejected. Reason: {reason}",
        )
    return payment, reservation

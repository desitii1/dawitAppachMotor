import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity import ActivityLog
from app.models.admin import AdminUser
from app.models.customer import Customer
from app.models.conversation_message import ConversationMessage
from app.models.lottery import Lottery
from app.models.payment import Payment, PaymentAttachment
from app.models.reservation import Reservation
from app.models.reservation import ReservationItem
from app.models.ticket import Ticket
from app.security.authentication import get_current_admin
from app.services.conversation_service import send_customer_message


router = APIRouter(prefix="/admin/customers", tags=["customers"])
logger = logging.getLogger(__name__)


class CustomerMessageCreate(BaseModel):
    message_text: str = Field(min_length=1, max_length=4096)


@router.get("")
def list_customers(
    search: str | None = None,
    sort: str = "activity",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    query = select(Customer)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            Customer.full_name.ilike(term)
            | Customer.phone_number.contains(search.strip())
            | Customer.telegram_username.ilike(term)
        )

    if sort == "name":
        query = query.order_by(Customer.full_name.asc().nulls_last(), Customer.id.asc())
    else:
        query = query.order_by(Customer.last_activity_at.desc(), Customer.id.desc())

    total = db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0
    customers = db.scalars(
        query.offset((page - 1) * page_size).limit(page_size)
    ).all()

    result = []
    for customer in customers:
        purchased = db.scalar(
            select(func.count()).select_from(Ticket).where(
                Ticket.customer_id == customer.id,
                Ticket.status == "SOLD",
            )
        ) or 0
        reserved = db.scalar(
            select(func.count()).select_from(Reservation).where(
                Reservation.customer_id == customer.id,
                Reservation.status.in_(("AWAITING_PAYMENT", "PAYMENT_SUBMITTED")),
            )
        ) or 0
        payments = db.scalar(
            select(func.count()).select_from(Payment).where(Payment.customer_id == customer.id)
        ) or 0
        result.append({
            "id": customer.id,
            "telegram_username": customer.telegram_username,
            "full_name": customer.full_name,
            "phone_number": customer.phone_number,
            "purchased_numbers": purchased,
            "active_reservations": reserved,
            "payments": payments,
            "created_at": customer.created_at,
            "last_activity_at": customer.last_activity_at,
        })
    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{customer_id}/messages")
def list_customer_messages(
    customer_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    messages = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.customer_id == customer_id)
        .order_by(ConversationMessage.sent_at, ConversationMessage.id)
    ).all()
    result = [
        {
            "id": message.id,
            "direction": message.direction,
            "message_text": message.message_text,
            "sent_at": message.sent_at,
            "telegram_message_id": message.telegram_message_id,
            "attachment_id": None,
        }
        for message in messages
    ]
    payment_attachments = db.execute(
        select(PaymentAttachment, Payment.reservation_id)
        .join(Payment, Payment.id == PaymentAttachment.payment_id)
        .where(Payment.customer_id == customer_id)
        .order_by(PaymentAttachment.uploaded_at, PaymentAttachment.id)
    ).all()
    reservation_ids = {reservation_id for _, reservation_id in payment_attachments}
    numbers_by_reservation: dict[int, list[str]] = {}
    if reservation_ids:
        reservation_numbers = db.execute(
            select(ReservationItem.reservation_id, Ticket.number)
            .join(Ticket, Ticket.id == ReservationItem.ticket_id)
            .where(ReservationItem.reservation_id.in_(reservation_ids))
            .order_by(ReservationItem.reservation_id, Ticket.number)
        ).all()
        for reservation_id, number in reservation_numbers:
            numbers_by_reservation.setdefault(reservation_id, []).append(number)

    for attachment, reservation_id in payment_attachments:
        numbers = numbers_by_reservation.get(reservation_id, [])
        description = (
            f"Payment image sent for numbers: {', '.join(numbers)}"
            if numbers
            else "Payment image sent"
        )
        result.append({
            "id": f"payment-attachment-{attachment.id}",
            "direction": "INBOUND",
            "message_text": description,
            "sent_at": attachment.uploaded_at,
            "telegram_message_id": None,
            "attachment_id": attachment.id,
        })
    return sorted(result, key=lambda message: message["sent_at"])


@router.post("/{customer_id}/messages", status_code=201)
def send_customer_conversation_message(
    customer_id: int,
    payload: CustomerMessageCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    message_text = payload.message_text.strip()
    if not message_text:
        raise HTTPException(status_code=422, detail="Message cannot be blank")
    try:
        message = send_customer_message(
            db,
            customer=customer,
            admin_user_id=admin.id,
            message_text=message_text,
        )
    except (TelegramAPIError, RuntimeError) as exc:
        logger.exception("Could not send admin message to customer_id=%s", customer_id)
        if isinstance(exc, TelegramBadRequest) and "chat not found" in str(exc).casefold():
            detail = (
                "Telegram cannot find this chat. Ask the customer to open this bot and "
                "press Start, then try again. If they have already done that, verify "
                "their Telegram ID and that this server is using the same bot."
            )
        else:
            detail = f"Telegram could not deliver the message: {exc}"
        raise HTTPException(
            status_code=502,
            detail=detail,
        ) from exc
    return {
        "id": message.id,
        "direction": message.direction,
        "message_text": message.message_text,
        "sent_at": message.sent_at,
        "telegram_message_id": message.telegram_message_id,
    }


@router.get("/{customer_id}")
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    reservations = db.scalars(
        select(Reservation)
        .where(Reservation.customer_id == customer_id)
        .order_by(Reservation.created_at.desc())
    ).all()
    reservation_history = []
    for reservation in reservations:
        numbers = db.scalars(
            select(Ticket.number)
            .join(ReservationItem, ReservationItem.ticket_id == Ticket.id)
            .where(ReservationItem.reservation_id == reservation.id)
            .order_by(Ticket.number)
        ).all()
        reservation_history.append({
            "id": reservation.id,
            "status": reservation.status,
            "total_amount": reservation.total_amount,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
            "numbers": list(numbers),
        })

    numbers_by_reservation = {
        reservation["id"]: reservation["numbers"]
        for reservation in reservation_history
    }
    payments = db.scalars(
        select(Payment)
        .where(Payment.customer_id == customer_id)
        .order_by(Payment.submitted_at.desc().nulls_last())
    ).all()
    attachments_by_payment: dict[int, list[PaymentAttachment]] = {}
    if payments:
        attachments = db.scalars(
            select(PaymentAttachment)
            .where(PaymentAttachment.payment_id.in_([payment.id for payment in payments]))
            .order_by(PaymentAttachment.uploaded_at, PaymentAttachment.id)
        ).all()
        for attachment in attachments:
            attachments_by_payment.setdefault(attachment.payment_id, []).append(attachment)
    activities = db.scalars(
        select(ActivityLog)
        .where(ActivityLog.customer_id == customer_id)
        .order_by(ActivityLog.created_at.desc())
    ).all()
    purchased_numbers = db.scalars(
        select(Ticket.number)
        .where(Ticket.customer_id == customer_id, Ticket.status == "SOLD")
        .order_by(Ticket.number)
    ).all()
    purchased_tickets = db.execute(
        select(Ticket.number, Ticket.sold_at, Lottery.name)
        .join(Lottery, Lottery.id == Ticket.lottery_id)
        .where(Ticket.customer_id == customer_id, Ticket.status == "SOLD")
        .order_by(Ticket.sold_at.desc().nullslast(), Ticket.id.desc())
    ).all()

    return {
        "id": customer.id,
        "telegram_username": customer.telegram_username,
        "full_name": customer.full_name,
        "phone_number": customer.phone_number,
        "created_at": customer.created_at,
        "last_activity_at": customer.last_activity_at,
        "purchased_numbers": list(purchased_numbers),
        "purchased_tickets": [
            {"number": number, "sold_at": sold_at, "lottery_name": lottery_name}
            for number, sold_at, lottery_name in purchased_tickets
        ],
        "reservations": reservation_history,
        "payments": [
            {
                "id": payment.id,
                "amount": payment.amount,
                "status": payment.status,
                "rejection_reason": payment.rejection_reason,
                "submitted_at": payment.submitted_at,
                "approved_at": payment.approved_at,
                "numbers": numbers_by_reservation.get(payment.reservation_id, []),
                "attachments": [
                    {
                        "id": attachment.id,
                        "uploaded_at": attachment.uploaded_at,
                        "original_filename": attachment.original_filename,
                    }
                    for attachment in attachments_by_payment.get(payment.id, [])
                ],
            }
            for payment in payments
        ],
        "activities": [
            {
                "id": activity.id,
                "activity_type": activity.activity_type,
                "description": activity.description,
                "created_at": activity.created_at,
            }
            for activity in activities
        ],
    }

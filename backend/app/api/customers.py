from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity import ActivityLog
from app.models.admin import AdminUser
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.reservation import ReservationItem
from app.models.ticket import Ticket
from app.security.authentication import get_current_admin


router = APIRouter(prefix="/admin/customers", tags=["customers"])


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
            "telegram_id": customer.telegram_id,
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
            "reference": reservation.reference,
            "status": reservation.status,
            "total_amount": reservation.total_amount,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
            "numbers": list(numbers),
        })

    payments = db.scalars(
        select(Payment)
        .where(Payment.customer_id == customer_id)
        .order_by(Payment.submitted_at.desc().nulls_last())
    ).all()
    activities = db.scalars(
        select(ActivityLog)
        .where(ActivityLog.customer_id == customer_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(100)
    ).all()
    purchased_numbers = db.scalars(
        select(Ticket.number)
        .where(Ticket.customer_id == customer_id, Ticket.status == "SOLD")
        .order_by(Ticket.number)
    ).all()

    return {
        "id": customer.id,
        "telegram_id": customer.telegram_id,
        "telegram_username": customer.telegram_username,
        "full_name": customer.full_name,
        "phone_number": customer.phone_number,
        "created_at": customer.created_at,
        "last_activity_at": customer.last_activity_at,
        "purchased_numbers": list(purchased_numbers),
        "reservations": reservation_history,
        "payments": [
            {
                "id": payment.id,
                "reservation_id": payment.reservation_id,
                "amount": payment.amount,
                "status": payment.status,
                "rejection_reason": payment.rejection_reason,
                "submitted_at": payment.submitted_at,
                "approved_at": payment.approved_at,
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

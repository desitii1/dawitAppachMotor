from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.customer import Customer
from app.models.lottery import Lottery
from app.models.payment import Payment
from app.models.reservation import Reservation, ReservationItem
from app.models.ticket import Ticket


ACTIVE_RESERVATION_STATUSES = ("AWAITING_PAYMENT", "PAYMENT_SUBMITTED")


class ReservationError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def normalize_phone_number(value: str) -> str:
    compact = value.strip().replace(" ", "").replace("-", "")
    if compact.startswith("+251"):
        compact = "0" + compact[4:]
    elif compact.startswith("251"):
        compact = "0" + compact[3:]
    if not compact.isdigit() or len(compact) != 10 or not compact.startswith("09"):
        raise ReservationError("Phone number must be in 09XXXXXXXX, +2519XXXXXXXX, or 2519XXXXXXXX format")
    return compact


def expire_reservations(db: Session, now: datetime | None = None, commit: bool = True) -> int:
    now = now or datetime.now(timezone.utc)
    expired = db.scalars(
        select(Reservation)
        .where(
            Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
            Reservation.expires_at <= now,
        )
        .with_for_update()
    ).all()

    released = 0
    for reservation in expired:
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
        reservation.status = "EXPIRED"
        payment = db.scalar(select(Payment).where(Payment.reservation_id == reservation.id).with_for_update())
        if payment and payment.status != "APPROVED":
            payment.status = "EXPIRED"
        released += len(tickets)
    if commit:
        db.commit()
    return released


def create_reservation(
    db: Session,
    *,
    telegram_id: int,
    telegram_username: str | None,
    full_name: str,
    phone_number: str,
    lottery_id: int,
    numbers: list[str],
) -> Reservation:
    normalized_phone = normalize_phone_number(phone_number)

    lottery = db.execute(
        select(Lottery).where(Lottery.id == lottery_id).with_for_update()
    ).scalar_one_or_none()
    if lottery is None:
        raise ReservationError("Lottery not found", 404)
    if lottery.status != "ACTIVE":
        raise ReservationError("This lottery is not accepting reservations")

    customer = db.execute(
        select(Customer).where(Customer.telegram_id == telegram_id).with_for_update()
    ).scalar_one_or_none()
    if customer is None:
        customer = Customer(
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            full_name=full_name,
            phone_number=normalized_phone,
        )
        db.add(customer)
        db.flush()
    else:
        customer.telegram_username = telegram_username
        customer.full_name = full_name
        customer.phone_number = normalized_phone
        customer.last_activity_at = datetime.now(timezone.utc)

    expire_reservations(db, commit=False)

    active_ticket_count = count_customer_allocation(db, customer.id, lottery_id)
    remaining = lottery.max_numbers_per_customer - active_ticket_count
    if remaining <= 0:
        raise ReservationError(
            f"You can select a maximum of {lottery.max_numbers_per_customer} numbers per lottery. "
            f"You currently have {active_ticket_count} numbers reserved or purchased."
        )

    unique_numbers = list(dict.fromkeys(numbers))
    if len(unique_numbers) > remaining:
        raise ReservationError(
            f"You can select a maximum of {lottery.max_numbers_per_customer} numbers per lottery. "
            f"You currently have {active_ticket_count} numbers reserved or purchased "
            f"and can select only {remaining} more."
        )

    tickets = db.execute(
        select(Ticket)
        .where(
            Ticket.lottery_id == lottery_id,
            Ticket.number.in_(unique_numbers),
        )
        .order_by(Ticket.number)
        .with_for_update()
    ).scalars().all()
    found = {ticket.number for ticket in tickets}
    unavailable = [number for number in unique_numbers if number not in found]
    unavailable.extend(number for number in found if next(ticket for ticket in tickets if ticket.number == number).status != "AVAILABLE")
    unavailable = list(dict.fromkeys(unavailable))
    if unavailable:
        raise ReservationError(
            f"These numbers are unavailable: {', '.join(unavailable)}",
            409,
        )
    if len(tickets) != len(unique_numbers):
        missing = [number for number in unique_numbers if number not in found]
        raise ReservationError(f"These numbers do not exist: {', '.join(missing)}", 404)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=lottery.reservation_duration_hours)
    reservation = Reservation(
        reference=f"RES-{secrets.randbelow(900000) + 100000}",
        customer_id=customer.id,
        lottery_id=lottery_id,
        status="AWAITING_PAYMENT",
        total_amount=lottery.ticket_price * len(tickets),
        expires_at=expires_at,
        created_at=now,
    )
    db.add(reservation)
    db.flush()

    db.add_all(
        ReservationItem(reservation_id=reservation.id, ticket_id=ticket.id)
        for ticket in tickets
    )
    for ticket in tickets:
        ticket.status = "RESERVED"
        ticket.reservation_id = reservation.id
        ticket.customer_id = customer.id
    db.add(
        Payment(
            reservation_id=reservation.id,
            customer_id=customer.id,
            amount=reservation.total_amount,
            status="AWAITING_PAYMENT",
        )
    )
    db.add(
        ActivityLog(
            customer_id=customer.id,
            activity_type="RESERVATION_CREATED",
            description=(
                f"Reserved numbers {', '.join(ticket.number for ticket in tickets)} "
                f"for lottery {lottery.name}"
            ),
        )
    )
    customer.last_activity_at = now
    db.commit()
    db.refresh(reservation)
    return reservation


def count_customer_allocation(db: Session, customer_id: int, lottery_id: int) -> int:
    from sqlalchemy import func

    sold_count = db.scalar(
        select(func.count(Ticket.id)).where(
            Ticket.lottery_id == lottery_id,
            Ticket.customer_id == customer_id,
            Ticket.status == "SOLD",
        )
    ) or 0

    reserved_count = db.scalar(
        select(func.count(ReservationItem.ticket_id))
        .join(Reservation, Reservation.id == ReservationItem.reservation_id)
        .where(
            Reservation.customer_id == customer_id,
            Reservation.lottery_id == lottery_id,
            Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        )
    ) or 0
    return sold_count + reserved_count

from datetime import datetime, timezone
import secrets

from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.lottery import (
    LotteryCreate,
    LotteryResponse,
    LotteryUpdate,
    ManagedTicketPageResponse,
    TicketPageResponse,
)
from app.services import lottery_service
from app.models.admin import AdminUser
from app.models.activity import ActivityLog
from app.models.customer import Customer
from app.models.ticket import Ticket
from app.security.authentication import get_current_admin
from app.services.reservation_service import ReservationError, normalize_phone_number


router = APIRouter(prefix="/lotteries", tags=["lotteries"])


class ManagedTicketUpdate(BaseModel):
    status: str | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if value not in {"AVAILABLE", "RESERVED", "SOLD"}:
            raise ValueError("status must be AVAILABLE, RESERVED, or SOLD")
        return value

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("full_name cannot be blank")
        return value

    @field_validator("phone_number")
    @classmethod
    def clean_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return normalize_phone_number(value)
        except ReservationError as exc:
            raise ValueError(exc.message) from exc



@router.post("", response_model=LotteryResponse, status_code=status.HTTP_201_CREATED)
def create_lottery(payload: LotteryCreate, db: Session = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    try:
        return lottery_service.create_lottery(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[LotteryResponse])
def list_lotteries(db: Session = Depends(get_db)):
    return lottery_service.list_lotteries(db)


@router.get("/{lottery_id}", response_model=LotteryResponse)
def get_lottery(lottery_id: int, db: Session = Depends(get_db)):
    lottery = lottery_service.get_lottery(db, lottery_id)
    if lottery is None:
        raise HTTPException(status_code=404, detail="Lottery not found")
    return lottery


@router.patch("/{lottery_id}", response_model=LotteryResponse)
def update_lottery(lottery_id: int, payload: LotteryUpdate, db: Session = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    lottery = lottery_service.get_lottery(db, lottery_id)
    if lottery is None:
        raise HTTPException(status_code=404, detail="Lottery not found")
    try:
        return lottery_service.update_lottery(
            db,
            lottery,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{lottery_id}/tickets", response_model=TicketPageResponse)
def list_tickets(
    lottery_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    if lottery_service.get_lottery(db, lottery_id) is None:
        raise HTTPException(status_code=404, detail="Lottery not found")
    try:
        items, total, pages = lottery_service.list_tickets(
            db,
            lottery_id,
            page,
            page_size,
            status,
            search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


@router.get(
    "/{lottery_id}/tickets/manage",
    response_model=ManagedTicketPageResponse,
)
def list_managed_tickets(
    lottery_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    if lottery_service.get_lottery(db, lottery_id) is None:
        raise HTTPException(status_code=404, detail="Lottery not found")
    items, total, pages = lottery_service.list_tickets(
        db, lottery_id, page, page_size, None, None
    )
    customer_ids = {ticket.customer_id for ticket in items if ticket.customer_id}
    customers = (
        db.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()
        if customer_ids
        else []
    )
    customers_by_id = {customer.id: customer for customer in customers}
    return {
        "items": [
            {
                "id": ticket.id,
                "number": ticket.number,
                "status": ticket.status,
                "customer_name": (
                    customers_by_id[ticket.customer_id].full_name
                    if ticket.customer_id in customers_by_id
                    else None
                ),
                "phone_number": (
                    customers_by_id[ticket.customer_id].phone_number
                    if ticket.customer_id in customers_by_id
                    else None
                ),
            }
            for ticket in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


@router.patch("/{lottery_id}/tickets/{ticket_id}")
def update_managed_ticket(
    lottery_id: int,
    ticket_id: int,
    payload: ManagedTicketUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    ticket = db.scalar(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.lottery_id == lottery_id,
        ).with_for_update()
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if payload.status == "RESERVED" and ticket.status != "RESERVED":
        raise HTTPException(
            status_code=409,
            detail="Numbers can only become reserved through customer reservations.",
        )
    if (
        payload.status is None
        and payload.full_name is None
        and payload.phone_number is None
    ):
        raise HTTPException(status_code=422, detail="At least one field must be provided.")

    if ticket.status == "RESERVED" and payload.status not in {None, "RESERVED"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "This number belongs to an active reservation. Resolve the reservation "
                "through payment review before changing its status."
            ),
        )

    customer = db.get(Customer, ticket.customer_id) if ticket.customer_id else None
    if ticket.status in {"SOLD", "RESERVED"} and customer is None:
        raise HTTPException(
            status_code=409,
            detail="This number has no customer record to update.",
        )

    old_status = ticket.status
    target_status = payload.status or ticket.status
    if target_status == "SOLD" and ticket.status == "AVAILABLE":
        if payload.full_name is None or payload.phone_number is None:
            raise HTTPException(
                status_code=422,
                detail="Customer name and phone number are required to manually sell a number.",
            )
        telegram_id = -secrets.randbelow(2**62) - 1
        while db.scalar(
            select(Customer.id).where(Customer.telegram_id == telegram_id)
        ) is not None:
            telegram_id = -secrets.randbelow(2**62) - 1
        customer = Customer(
            telegram_id=telegram_id,
            telegram_username="manual-sale",
            full_name=payload.full_name,
            phone_number=payload.phone_number,
        )
        db.add(customer)
        db.flush()
        ticket.status = "SOLD"
        ticket.customer_id = customer.id
        ticket.reservation_id = None
        ticket.sold_at = datetime.now(timezone.utc)
    elif target_status == "AVAILABLE":
        ticket.status = "AVAILABLE"
        ticket.reservation_id = None
        ticket.customer_id = None
        ticket.sold_at = None
    else:
        if payload.full_name is not None:
            customer.full_name = payload.full_name
        if payload.phone_number is not None:
            customer.phone_number = payload.phone_number
        ticket.status = target_status
        if target_status == "SOLD":
            ticket.reservation_id = None
            ticket.sold_at = ticket.sold_at or datetime.now(timezone.utc)

    if customer is not None:
        customer.last_activity_at = datetime.now(timezone.utc)
    if old_status != ticket.status or payload.full_name is not None or payload.phone_number is not None:
        db.add(
            ActivityLog(
                customer_id=customer.id if customer else None,
                admin_user_id=admin.id,
                activity_type="TICKET_UPDATED",
                description=(
                    f"Admin updated number {ticket.number}: "
                    f"status {old_status} to {ticket.status}"
                    + (
                        f"; customer {customer.full_name}, phone {customer.phone_number}"
                        if customer
                        else ""
                    )
                ),
            )
        )
    db.commit()
    current_customer = db.get(Customer, ticket.customer_id) if ticket.customer_id else None
    return {
        "id": ticket.id,
        "number": ticket.number,
        "status": ticket.status,
        "customer_name": current_customer.full_name if current_customer else None,
        "phone_number": current_customer.phone_number if current_customer else None,
    }

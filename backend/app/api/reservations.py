from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.reservation import ReservationCreate, ReservationResponse
from app.services.reservation_service import ReservationError, create_reservation, expire_reservations
from sqlalchemy import select
from app.models.admin import AdminUser
from app.models.reservation import Reservation
from app.models.reservation import ReservationItem
from app.models.ticket import Ticket
from app.models.customer import Customer
from app.security.authentication import get_current_admin


router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post("", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def reserve(payload: ReservationCreate, db: Session = Depends(get_db)):
    try:
        return create_reservation(db, **payload.model_dump())
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/expire", status_code=status.HTTP_200_OK)
def expire(db: Session = Depends(get_db)):
    released = expire_reservations(db)
    return {"released_ticket_count": released}


@router.get("/admin/list")
def admin_list(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    reservations = db.scalars(
        select(Reservation).order_by(Reservation.created_at.desc()).limit(200)
    ).all()
    result = []
    for reservation in reservations:
        customer = db.get(Customer, reservation.customer_id)
        numbers = db.scalars(
            select(Ticket.number)
            .join(ReservationItem, ReservationItem.ticket_id == Ticket.id)
            .where(ReservationItem.reservation_id == reservation.id)
            .order_by(Ticket.number)
        ).all()
        result.append({
            "id": reservation.id,
            "reference": reservation.reference,
            "status": reservation.status,
            "total_amount": reservation.total_amount,
            "expires_at": reservation.expires_at,
            "created_at": reservation.created_at,
            "customer_name": customer.full_name if customer else None,
            "phone_number": customer.phone_number if customer else None,
            "numbers": list(numbers),
        })
    return result

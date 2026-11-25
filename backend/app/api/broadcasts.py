from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import AdminUser
from app.models.broadcast import Broadcast, BroadcastDelivery
from app.models.customer import Customer
from app.security.authentication import get_current_admin
from app.services.broadcast_service import (
    BroadcastError,
    create_broadcast,
    process_broadcast,
    retry_failed_deliveries,
)


class BroadcastCreate(BaseModel):
    message_text: str = Field(min_length=1, max_length=4096)
    customer_ids: list[int] | None = None


router = APIRouter(prefix="/admin/broadcasts", tags=["broadcasts"])


@router.get("/customers")
def list_customers(
    search: str | None = None,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    query = select(Customer)
    if search:
        query = query.where(
            Customer.full_name.ilike(f"%{search}%")
            | Customer.phone_number.contains(search)
            | Customer.telegram_username.ilike(f"%{search}%")
        )
    customers = db.scalars(query.order_by(Customer.last_activity_at.desc()).limit(200)).all()
    return [
        {
            "id": customer.id,
            "full_name": customer.full_name,
            "phone_number": customer.phone_number,
            "telegram_id": customer.telegram_id,
            "telegram_username": customer.telegram_username,
        }
        for customer in customers
    ]


@router.post("")
def create(
    payload: BroadcastCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    try:
        broadcast = create_broadcast(
            db,
            message_text=payload.message_text,
            customer_ids=payload.customer_ids,
        )
    except BroadcastError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "id": broadcast.id,
        "message_text": broadcast.message_text,
        "status": broadcast.status,
        "created_at": broadcast.created_at,
    }


@router.post("/{broadcast_id}/process")
def process(
    broadcast_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    try:
        broadcast = process_broadcast(db, broadcast_id)
    except BroadcastError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "id": broadcast.id,
        "status": broadcast.status,
        "completed_at": broadcast.completed_at,
    }


@router.post("/{broadcast_id}/retry")
def retry(
    broadcast_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    try:
        broadcast = retry_failed_deliveries(db, broadcast_id)
    except BroadcastError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "id": broadcast.id,
        "status": broadcast.status,
    }


@router.get("")
def history(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    broadcasts = db.scalars(
        select(Broadcast).order_by(Broadcast.created_at.desc()).limit(100)
    ).all()
    result = []
    for broadcast in broadcasts:
        deliveries = db.execute(
            select(BroadcastDelivery.delivery_status, BroadcastDelivery.error_message)
            .where(BroadcastDelivery.broadcast_id == broadcast.id)
        ).all()
        failed_customers = db.execute(
            select(Customer.full_name, Customer.telegram_username, BroadcastDelivery.error_message)
            .join(Customer, Customer.id == BroadcastDelivery.customer_id)
            .where(
                BroadcastDelivery.broadcast_id == broadcast.id,
                BroadcastDelivery.delivery_status == "FAILED",
            )
        ).all()
        result.append({
            "id": broadcast.id,
            "message_text": broadcast.message_text,
            "status": broadcast.status,
            "created_at": broadcast.created_at,
            "completed_at": broadcast.completed_at,
            "sent": sum(item.delivery_status == "SENT" for item in deliveries),
            "failed": sum(item.delivery_status == "FAILED" for item in deliveries),
            "pending": sum(item.delivery_status == "PENDING" for item in deliveries),
            "failures": [
                {
                    "customer": name or username or "Customer",
                    "error": error,
                }
                for name, username, error in failed_customers
            ],
        })
    return result

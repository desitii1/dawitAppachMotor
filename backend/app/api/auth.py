from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.admin import AdminUser
from app.models.customer import Customer
from app.models.lottery import Lottery
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.ticket import Ticket
from app.schemas.auth import AdminResponse, LoginRequest
from app.security.authentication import (
    SESSION_COOKIE_NAME,
    check_login_rate_limit,
    clear_failed_login,
    get_current_admin,
    record_failed_login,
    verify_password,
)


router = APIRouter(prefix="/admin", tags=["admin"])
serializer = URLSafeTimedSerializer(settings.session_secret)


def sign_admin_id(admin_id: int) -> str:
    return serializer.dumps({"admin_id": admin_id})


def read_admin_id(cookie_value: str) -> int:
    data = serializer.loads(cookie_value, max_age=12 * 60 * 60)
    return int(data["admin_id"])


@router.post("/login", response_model=AdminResponse)
def login(payload: LoginRequest, request: Request, response: Response, db=Depends(get_db)):
    rate_key = f"{request.client.host if request.client else 'unknown'}:{payload.username.lower()}"
    check_login_rate_limit(rate_key)

    admin = db.scalar(select(AdminUser).where(AdminUser.username == payload.username))
    if admin is None or not verify_password(admin.password_hash, payload.password):
        record_failed_login(rate_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    clear_failed_login(rate_key)
    admin.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(admin)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        sign_admin_id(admin.id),
        httponly=True,
        secure=settings.public_app_url.startswith("https://"),
        samesite="lax",
        max_age=12 * 60 * 60,
        path="/",
    )
    return admin


@router.get("/me", response_model=AdminResponse)
def me(admin: AdminUser = Depends(get_current_admin)):
    return admin


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"status": "logged_out"}


@router.get("/overview")
def overview(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    return {
        "total_lotteries": db.scalar(select(func.count()).select_from(Lottery)) or 0,
        "available_numbers": db.scalar(select(func.count()).select_from(Ticket).where(Ticket.status == "AVAILABLE")) or 0,
        "reserved_numbers": db.scalar(select(func.count()).select_from(Ticket).where(Ticket.status == "RESERVED")) or 0,
        "sold_numbers": db.scalar(select(func.count()).select_from(Ticket).where(Ticket.status == "SOLD")) or 0,
        "total_customers": db.scalar(select(func.count()).select_from(Customer)) or 0,
        "pending_payments": db.scalar(
            select(func.count()).select_from(Payment).where(Payment.status == "PAYMENT_SUBMITTED")
        ) or 0,
        "approved_payments": db.scalar(
            select(func.count()).select_from(Payment).where(Payment.status == "APPROVED")
        ) or 0,
        "approved_revenue": float(
            db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0))
                .where(Payment.status == "APPROVED")
            ) or 0
        ),
        "recent_reservations": db.scalar(select(func.count()).select_from(Reservation)) or 0,
    }

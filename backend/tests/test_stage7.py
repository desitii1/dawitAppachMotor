from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models.admin import AdminUser
from app.models.customer import Customer
from app.models.lottery import Lottery
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.ticket import Ticket
from app.security.authentication import hash_password
from app.services.payment_service import (
    PaymentReviewError,
    approve_payment,
    reject_payment,
)
from app.services.reservation_service import create_reservation


client = TestClient(app)


def create_admin_and_reservation(prefix: str, expire: bool = False):
    db = SessionLocal()
    try:
        admin = db.scalar(select(AdminUser).where(AdminUser.username == f"{prefix}-owner"))
        if admin is None:
            admin = AdminUser(
                username=f"{prefix}-owner",
                password_hash=hash_password("Stage7-Secure-Password"),
            )
            db.add(admin)
            db.flush()

        lottery = Lottery(
            name=f"{prefix} lottery",
            start_number=70,
            end_number=72,
            ticket_price=100,
            currency="ETB",
            reservation_duration_hours=24,
            max_numbers_per_customer=100,
            status="ACTIVE",
        )
        db.add(lottery)
        db.flush()
        db.add_all(
            Ticket(lottery_id=lottery.id, number=f"{number:03d}", status="AVAILABLE")
            for number in range(70, 73)
        )
        db.commit()

        reservation = create_reservation(
            db,
            telegram_id=int(prefix[-6:].isdigit() and prefix[-6:] or "970001"),
            telegram_username=prefix,
            full_name="Stage Seven Customer",
            phone_number="0912345678",
            lottery_id=lottery.id,
            numbers=["070"],
        )
        payment = db.scalar(select(Payment).where(Payment.reservation_id == reservation.id))
        payment.status = "PAYMENT_SUBMITTED"
        payment.submitted_at = datetime.now(timezone.utc)
        reservation.status = "PAYMENT_SUBMITTED"
        if expire:
            reservation.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        db.refresh(admin)
        return admin.id, payment.id
    finally:
        db.close()


def test_payment_approval_marks_number_sold():
    admin_id, payment_id = create_admin_and_reservation("970001")
    db = SessionLocal()
    try:
        admin = db.get(AdminUser, admin_id)
        payment, reservation = approve_payment(
            db,
            payment_id=payment_id,
            admin=admin,
        )
        assert payment.status == "APPROVED"
        assert reservation.status == "APPROVED"
        ticket = db.scalar(
            select(Ticket).where(Ticket.reservation_id == reservation.id)
        )
        assert ticket.status == "SOLD"
        assert ticket.sold_at is not None
    finally:
        db.close()


def test_expired_reservation_requires_explicit_review():
    admin_id, payment_id = create_admin_and_reservation("970002", expire=True)
    db = SessionLocal()
    try:
        admin = db.get(AdminUser, admin_id)
        try:
            approve_payment(db, payment_id=payment_id, admin=admin)
            assert False, "Expired payment approval should be rejected"
        except PaymentReviewError as exc:
            assert exc.status_code == 409

        payment, reservation = approve_payment(
            db,
            payment_id=payment_id,
            admin=admin,
            allow_expired_explicit=True,
        )
        assert payment.status == "APPROVED"
        assert reservation.status == "APPROVED"
    finally:
        db.close()


def test_rejection_releases_reserved_number():
    admin_id, payment_id = create_admin_and_reservation("970003")
    db = SessionLocal()
    try:
        admin = db.get(AdminUser, admin_id)
        payment, reservation = reject_payment(
            db,
            payment_id=payment_id,
            admin=admin,
            rejection_reason="Payment screenshot is unclear",
        )
        assert payment.status == "REJECTED"
        assert reservation.status == "REJECTED"
        ticket = db.scalar(
            select(Ticket).where(Ticket.reservation_id.is_(None), Ticket.number == "070")
        )
        assert ticket.status == "AVAILABLE"
        assert ticket.customer_id is None
    finally:
        db.close()

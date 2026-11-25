from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models.admin import AdminUser
from app.models.customer import Customer
from app.models.lottery import Lottery
from app.models.payment import Payment, PaymentAttachment
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


def test_payment_attachment_is_served_inline_to_authenticated_admin(tmp_path, monkeypatch):
    admin_id, payment_id = create_admin_and_reservation("971111")
    image = b"\x89PNG\r\n\x1a\npayment-test"
    storage_key = "payments/test/payment.png"
    attachment_path = tmp_path / storage_key
    attachment_path.parent.mkdir(parents=True)
    attachment_path.write_bytes(image)

    db = SessionLocal()
    try:
        db.add(
            PaymentAttachment(
                payment_id=payment_id,
                storage_key=storage_key,
                original_filename="payment.png",
            )
        )
        db.commit()
        attachment = db.scalar(
            select(PaymentAttachment).where(PaymentAttachment.payment_id == payment_id)
        )
        attachment_id = attachment.id
        customer_id = db.get(Payment, payment_id).customer_id
        admin = db.get(AdminUser, admin_id)
        username = admin.username
    finally:
        db.close()

    from app.config import settings

    monkeypatch.setattr(settings, "attachment_root", str(tmp_path))
    session = TestClient(app)
    login = session.post(
        "/admin/login",
        json={"username": username, "password": "Stage7-Secure-Password"},
    )
    assert login.status_code == 200

    response = session.get(f"/admin/payments/{payment_id}/attachment")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.content == image

    profile = session.get(f"/admin/customers/{customer_id}")
    assert profile.status_code == 200
    payment_record = profile.json()["payments"][0]
    assert payment_record["status"] == "PAYMENT_SUBMITTED"
    assert payment_record["numbers"] == ["070"]
    assert payment_record["attachments"][0]["id"] == attachment_id

    messages = session.get(f"/admin/customers/{customer_id}/messages")
    assert messages.status_code == 200
    payment_message = next(
        message for message in messages.json()
        if message["attachment_id"] == attachment_id
    )
    assert payment_message["direction"] == "INBOUND"
    assert payment_message["message_text"] == "Payment image sent for numbers: 070"

    conversation_image = session.get(
        f"/admin/payments/attachments/{attachment_id}"
    )
    assert conversation_image.status_code == 200
    assert conversation_image.content == image

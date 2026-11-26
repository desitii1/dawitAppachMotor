from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models.activity import ActivityLog
from app.models.admin import AdminUser
from app.models.customer import Customer
from app.models.lottery import Lottery
from app.models.payment import Payment, PaymentAttachment
from app.models.reservation import Reservation, ReservationItem
from app.models.ticket import Ticket
from app.security.authentication import hash_password
from app.services.payment_service import submit_payment_screenshot


def test_admin_can_edit_sold_ticket_release_and_manually_sell_available_ticket():
    username = "stage12-admin"
    password = "Stage12-Secure-Password"
    db = SessionLocal()
    try:
        customer = Customer(
            telegram_id=99121201,
            telegram_username="stage12-customer",
            full_name="Before Correction",
            phone_number="0911111111",
        )
        admin = AdminUser(username=username, password_hash=hash_password(password))
        lottery = Lottery(
            name="Stage 12 correction lottery",
            start_number=1,
            end_number=2,
            ticket_price=100,
            currency="ETB",
            reservation_duration_hours=24,
            max_numbers_per_customer=10,
            status="ACTIVE",
        )
        db.add_all([customer, admin, lottery])
        db.flush()
        ticket = Ticket(
            lottery_id=lottery.id,
            number="1",
            status="SOLD",
            customer_id=customer.id,
            sold_at=datetime.now(timezone.utc),
        )
        available_ticket = Ticket(
            lottery_id=lottery.id,
            number="2",
            status="AVAILABLE",
        )
        db.add_all([ticket, available_ticket])
        db.commit()
        customer_id = customer.id
        lottery_id = lottery.id
        ticket_id = ticket.id
        available_ticket_id = available_ticket.id
        admin_id = admin.id
    finally:
        db.close()

    client = TestClient(app)
    try:
        login = client.post(
            "/admin/login",
            json={"username": username, "password": password},
        )
        assert login.status_code == 200

        managed = client.get(f"/lotteries/{lottery_id}/tickets/manage")
        assert managed.status_code == 200
        assert managed.json()["items"][0]["customer_name"] == "Before Correction"
        assert managed.json()["items"][0]["phone_number"] == "0911111111"

        invalid_phone = client.patch(
            f"/lotteries/{lottery_id}/tickets/{ticket_id}",
            json={"phone_number": "123"},
        )
        assert invalid_phone.status_code == 422

        updated = client.patch(
            f"/lotteries/{lottery_id}/tickets/{ticket_id}",
            json={
                "status": "SOLD",
                "full_name": "Corrected Customer",
                "phone_number": "+251912345678",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "SOLD"
        assert updated.json()["customer_name"] == "Corrected Customer"
        assert updated.json()["phone_number"] == "0912345678"

        released = client.patch(
            f"/lotteries/{lottery_id}/tickets/{ticket_id}",
            json={"status": "AVAILABLE"},
        )
        assert released.status_code == 200
        assert released.json()["status"] == "AVAILABLE"
        assert released.json()["customer_name"] is None

        missing_customer = client.patch(
            f"/lotteries/{lottery_id}/tickets/{available_ticket_id}",
            json={"status": "SOLD"},
        )
        assert missing_customer.status_code == 422
        manual_sale = client.patch(
            f"/lotteries/{lottery_id}/tickets/{available_ticket_id}",
            json={
                "status": "SOLD",
                "full_name": "Manual Buyer",
                "phone_number": "0912345678",
            },
        )
        assert manual_sale.status_code == 200
        assert manual_sale.json()["status"] == "SOLD"
        assert manual_sale.json()["customer_name"] == "Manual Buyer"
        assert manual_sale.json()["phone_number"] == "0912345678"
        manual_customer_id = None

        activities = client.get("/admin/activities?page_size=100")
        assert activities.status_code == 200
        event = next(
            item for item in activities.json()
            if item["activity_type"] == "TICKET_UPDATED"
            and item["customer_id"] == customer_id
        )
        assert event["customer_name"] == "Corrected Customer"
        assert event["phone_number"] == "0912345678"
        assert "number 1" in event["description"]

        db = SessionLocal()
        try:
            ticket = db.get(Ticket, ticket_id)
            customer = db.get(Customer, customer_id)
            assert ticket.status == "AVAILABLE"
            assert ticket.customer_id is None
            assert customer.full_name == "Corrected Customer"
            assert customer.phone_number == "0912345678"
            sold_ticket = db.get(Ticket, available_ticket_id)
            manual_customer_id = sold_ticket.customer_id
            assert sold_ticket.status == "SOLD"
            assert manual_customer_id is not None
            assert db.get(Customer, manual_customer_id).telegram_id < 0
            assert db.get(AdminUser, admin_id) is not None
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            customer_ids = [customer_id]
            if manual_customer_id is not None:
                customer_ids.append(manual_customer_id)
            db.query(ActivityLog).filter(ActivityLog.customer_id.in_(customer_ids)).delete(
                synchronize_session=False
            )
            db.query(Ticket).filter(Ticket.lottery_id == lottery_id).delete(
                synchronize_session=False
            )
            db.query(Customer).filter(Customer.id.in_(customer_ids)).delete(
                synchronize_session=False
            )
            db.query(Lottery).filter(Lottery.id == lottery_id).delete(
                synchronize_session=False
            )
            db.query(AdminUser).filter(AdminUser.username == username).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()


def test_replacing_screenshot_removes_previous_attachment(tmp_path):
    db = SessionLocal()
    try:
        customer = Customer(
            telegram_id=99121202,
            telegram_username="stage12-payment",
            full_name="Screenshot Customer",
            phone_number="0911111111",
        )
        lottery = Lottery(
            name="Stage 12 screenshot lottery",
            start_number=2,
            end_number=2,
            ticket_price=100,
            currency="ETB",
            reservation_duration_hours=24,
            max_numbers_per_customer=10,
            status="ACTIVE",
        )
        db.add_all([customer, lottery])
        db.flush()
        reservation = Reservation(
            reference="RES-STAGE12-SCREENSHOT",
            customer_id=customer.id,
            lottery_id=lottery.id,
            status="PAYMENT_SUBMITTED",
            total_amount=100,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        )
        db.add(reservation)
        db.flush()
        payment = Payment(
            reservation_id=reservation.id,
            customer_id=customer.id,
            amount=100,
            status="PAYMENT_SUBMITTED",
        )
        ticket = Ticket(
            lottery_id=lottery.id,
            number="2",
            status="RESERVED",
            reservation_id=reservation.id,
            customer_id=customer.id,
        )
        db.add_all([payment, ticket])
        db.flush()
        db.add(ReservationItem(reservation_id=reservation.id, ticket_id=ticket.id))
        old_key = "payments/old/old.png"
        old_path = tmp_path / old_key
        old_path.parent.mkdir(parents=True)
        old_path.write_bytes(b"old")
        db.add(
            PaymentAttachment(
                payment_id=payment.id,
                storage_key=old_key,
                original_filename="old.png",
            )
        )
        db.commit()
        payment_id = payment.id
        customer_id = customer.id
        reservation_reference = reservation.reference

        submit_payment_screenshot(
            db,
            reservation_reference=reservation_reference,
            telegram_id=customer.telegram_id,
            content=b"replacement",
            content_type="image/png",
            original_filename="replacement.png",
            attachment_root=str(tmp_path),
            replace_existing=True,
        )

        attachments = db.scalars(
            select(PaymentAttachment).where(PaymentAttachment.payment_id == payment_id)
        ).all()
        assert len(attachments) == 1
        assert attachments[0].original_filename == "replacement.png"
        assert (tmp_path / attachments[0].storage_key).exists()
        assert not old_path.exists()
        assert db.scalar(
            select(ActivityLog).where(
                ActivityLog.customer_id == customer_id,
                ActivityLog.activity_type == "PAYMENT_SCREENSHOT_REPLACED",
            )
        )
    finally:
        if "customer_id" in locals():
            db.query(ActivityLog).filter(ActivityLog.customer_id == customer_id).delete(
                synchronize_session=False
            )
            db.query(PaymentAttachment).filter(
                PaymentAttachment.payment_id == payment_id
            ).delete(synchronize_session=False)
            db.query(ReservationItem).filter(
                ReservationItem.reservation_id == reservation.id
            ).delete(synchronize_session=False)
            db.query(Ticket).filter(Ticket.customer_id == customer_id).delete(
                synchronize_session=False
            )
            db.query(Payment).filter(Payment.id == payment_id).delete(
                synchronize_session=False
            )
            db.query(Reservation).filter(
                Reservation.reference == reservation_reference
            ).delete(synchronize_session=False)
            db.query(Customer).filter(Customer.id == customer_id).delete(
                synchronize_session=False
            )
            db.query(Lottery).filter(
                Lottery.name == "Stage 12 screenshot lottery"
            ).delete(synchronize_session=False)
            db.commit()
        db.close()

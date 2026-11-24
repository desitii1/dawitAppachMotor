from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.lottery import Lottery
from app.models.payment import Payment
from app.models.payment import PaymentAttachment
from app.models.reservation import Reservation
from app.models.reservation import ReservationItem
from app.models.ticket import Ticket
from app.services.reservation_service import create_reservation


client = TestClient(app)


def test_payment_screenshot_submission(tmp_path: Path):
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.telegram_id == 950001))
        if customer is not None:
            old_reservations = db.scalars(
                select(Reservation).where(Reservation.customer_id == customer.id)
            ).all()
            for old_reservation in old_reservations:
                db.query(PaymentAttachment).filter(
                    PaymentAttachment.payment_id.in_(
                        select(Payment.id).where(Payment.reservation_id == old_reservation.id)
                    )
                ).delete(synchronize_session=False)
                db.query(Payment).filter(Payment.reservation_id == old_reservation.id).delete(synchronize_session=False)
                db.query(ReservationItem).filter(
                    ReservationItem.reservation_id == old_reservation.id
                ).delete(synchronize_session=False)
                db.delete(old_reservation)
            db.flush()
            db.delete(customer)
        old_lottery = db.scalar(select(Lottery).where(Lottery.name == "Stage 5 Payment Lottery"))
        if old_lottery:
            db.query(Ticket).filter(Ticket.lottery_id == old_lottery.id).delete(synchronize_session=False)
            db.delete(old_lottery)
        db.commit()

        lottery = Lottery(
            name="Stage 5 Payment Lottery",
            start_number=50,
            end_number=54,
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
            for number in range(50, 55)
        )
        db.commit()

        reservation = create_reservation(
            db,
            telegram_id=950001,
            telegram_username="stage5",
            full_name="Payment Customer",
            phone_number="0912345678",
            lottery_id=lottery.id,
            numbers=["050"],
        )
        reference = reservation.reference
    finally:
        db.close()

    response = client.post(
        f"/payments/reservations/{reference}/screenshots",
        data={"telegram_id": "950001"},
        files={"file": ("screenshot.jpg", b"\xff\xd8\xfftest-image", "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["reservation_reference"] == reference
    assert body["status"] == "PAYMENT_SUBMITTED"

    db = SessionLocal()
    try:
        payment = db.scalar(select(Payment).where(Payment.reservation_id == reservation.id))
        assert payment.status == "PAYMENT_SUBMITTED"
        assert payment.submitted_at is not None
        reservation_db = db.get(Reservation, reservation.id)
        assert reservation_db.status == "PAYMENT_SUBMITTED"
    finally:
        db.close()

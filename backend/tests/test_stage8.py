from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models.activity import ActivityLog
from app.models.broadcast import Broadcast
from app.models.customer import Customer


client = TestClient(app)


def test_activity_log_creation_and_listing():
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.telegram_id == 980001))
        if customer is None:
            customer = Customer(
                telegram_id=980001,
                telegram_username="stage8",
                full_name="Stage Eight Customer",
                phone_number="0912345678",
            )
            db.add(customer)
            db.flush()
        db.add(
            ActivityLog(
                customer_id=customer.id,
                activity_type="BOT_STARTED",
                description="Customer started the Telegram bot",
            )
        )
        db.commit()
        customer_id = customer.id
    finally:
        db.close()

    login_db = SessionLocal()
    try:
        from app.commands.setup_admin import setup_admin
        setup_admin("stage8-owner", "Stage8-Secure-Password")
    finally:
        login_db.close()

    session = TestClient(app)
    login = session.post(
        "/admin/login",
        json={"username": "stage8-owner", "password": "Stage8-Secure-Password"},
    )
    assert login.status_code == 200

    activities = session.get("/admin/activities", params={"search": "Stage Eight"})
    assert activities.status_code == 200
    assert any(item["activity_type"] == "BOT_STARTED" for item in activities.json())

    broadcast = session.post(
        "/admin/broadcasts",
        json={"message_text": "Stage 8 broadcast test", "customer_ids": [customer_id]},
    )
    assert broadcast.status_code == 200
    broadcast_id = broadcast.json()["id"]

    processed = session.post(f"/admin/broadcasts/{broadcast_id}/process")
    assert processed.status_code == 200
    assert processed.json()["status"] in {"COMPLETED", "FAILED"}

    history = session.get("/admin/broadcasts")
    assert history.status_code == 200
    assert any(item["id"] == broadcast_id for item in history.json())

from fastapi.testclient import TestClient
from sqlalchemy import select
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage

import app.api.customers as customers_api
from app.database import SessionLocal
from app.main import app
from app.models.activity import ActivityLog
from app.models.admin import AdminUser
from app.models.conversation_message import ConversationMessage
from app.models.customer import Customer
from app.bot.handlers.customer import store_inbound_message
from app.security.authentication import hash_password


def test_customer_profile_and_conversation(monkeypatch):
    telegram_id = 991010
    username = "stage11-owner"
    password = "Stage11-Secure-Password"

    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
        if customer is None:
            customer = Customer(
                telegram_id=telegram_id,
                telegram_username="stage11-customer",
                full_name="Stage Eleven Customer",
                phone_number="0912345678",
            )
            db.add(customer)
            db.flush()
        customer_id = customer.id
        admin = db.scalar(select(AdminUser).where(AdminUser.username == username))
        if admin is None:
            admin = AdminUser(username=username, password_hash=hash_password(password))
            db.add(admin)
        db.add(
            ActivityLog(
                customer_id=customer_id,
                activity_type="BOT_STARTED",
                description="Customer started the Telegram bot",
            )
        )
        db.commit()
        admin_id = admin.id
    finally:
        db.close()

    assert store_inbound_message(
        telegram_id,
        1234,
        "I need help with my reservation.",
    )

    def fake_send_customer_message(db, *, customer, admin_user_id, message_text):
        sent = ConversationMessage(
            customer_id=customer.id,
            admin_user_id=admin_user_id,
            direction="OUTBOUND",
            message_text=message_text,
            telegram_message_id=12345,
        )
        db.add(sent)
        db.commit()
        db.refresh(sent)
        return sent

    monkeypatch.setattr(customers_api, "send_customer_message", fake_send_customer_message)

    try:
        session = TestClient(app)
        login = session.post(
            "/admin/login",
            json={"username": username, "password": password},
        )
        assert login.status_code == 200

        profile = session.get(f"/admin/customers/{customer_id}")
        assert profile.status_code == 200
        assert "telegram_id" not in profile.json()
        assert any(
            item["activity_type"] == "BOT_STARTED"
            for item in profile.json()["activities"]
        )

        messages = session.get(f"/admin/customers/{customer_id}/messages")
        assert messages.status_code == 200
        assert messages.json()[0]["direction"] == "INBOUND"

        customer_list = session.get("/admin/customers?page_size=100")
        assert customer_list.status_code == 200
        assert all("telegram_id" not in item for item in customer_list.json()["items"])

        for period, days in (
            ("weekly", 7),
            ("monthly", 30),
            ("two_months", 60),
            ("yearly", 365),
        ):
            report = session.get("/admin/reports", params={"period": period})
            assert report.status_code == 200
            report_body = report.json()
            assert report_body["period"] == period
            assert report_body["period_days"] == days
            assert report_body["period_start"] < report_body["period_end"]
            assert "numbers_sold" in report_body
            assert "new_customers" in report_body

        invalid_report = session.get(
            "/admin/reports",
            params={"period": "lifetime"},
        )
        assert invalid_report.status_code == 422

        sent = session.post(
            f"/admin/customers/{customer_id}/messages",
            json={"message_text": "We received your request."},
        )
        assert sent.status_code == 201
        assert sent.json()["direction"] == "OUTBOUND"
        assert sent.json()["telegram_message_id"] == 12345

        def fake_chat_not_found(db, *, customer, admin_user_id, message_text):
            raise TelegramBadRequest(
                method=SendMessage(chat_id=customer.telegram_id, text=message_text),
                message="Bad Request: chat not found",
            )

        monkeypatch.setattr(customers_api, "send_customer_message", fake_chat_not_found)
        failed = session.post(
            f"/admin/customers/{customer_id}/messages",
            json={"message_text": "Please check your payment."},
        )
        assert failed.status_code == 502
        assert "press Start" in failed.json()["detail"]
    finally:
        db = SessionLocal()
        try:
            customer = db.scalar(
                select(Customer).where(Customer.telegram_id == telegram_id)
            )
            admin = db.scalar(select(AdminUser).where(AdminUser.username == username))
            if customer:
                db.query(ConversationMessage).filter(
                    ConversationMessage.customer_id == customer.id
                ).delete(synchronize_session=False)
                db.query(ActivityLog).filter(
                    ActivityLog.customer_id == customer.id
                ).delete(synchronize_session=False)
                db.delete(customer)
            if admin:
                db.delete(admin)
            db.commit()
        finally:
            db.close()

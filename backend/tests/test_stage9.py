from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.admin import AdminUser
from app.models.customer import Customer
from app.security.authentication import hash_password
from sqlalchemy import select


client = TestClient(app)


def test_customer_directory_and_reports():
    db = SessionLocal()
    try:
        admin = db.scalar(select(AdminUser).where(AdminUser.username == "stage9-owner"))
        if admin is None:
            admin = AdminUser(
                username="stage9-owner",
                password_hash=hash_password("Stage9-Secure-Password"),
            )
            db.add(admin)

        existing = db.scalar(select(Customer).where(Customer.telegram_id == 990001))
        if existing is None:
            db.add(
                Customer(
                    telegram_id=990001,
                    telegram_username="stage9",
                    full_name="ዳዊት ተስቶ",
                    phone_number="0912345678",
                )
            )
        db.commit()
    finally:
        db.close()

    session = TestClient(app)
    login = session.post(
        "/admin/login",
        json={"username": "stage9-owner", "password": "Stage9-Secure-Password"},
    )
    assert login.status_code == 200

    customers = session.get("/admin/customers", params={"search": "ዳዊት", "sort": "name"})
    assert customers.status_code == 200
    assert customers.json()["total"] >= 1

    reports = session.get("/admin/reports")
    assert reports.status_code == 200
    body = reports.json()
    assert "confirmed_revenue" in body
    assert "lotteries" in body

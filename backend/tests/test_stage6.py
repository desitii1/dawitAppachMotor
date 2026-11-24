from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models.admin import AdminUser
from app.security.authentication import hash_password, verify_password


client = TestClient(app)


def test_admin_login_logout_and_cookie():
    db = SessionLocal()
    try:
        admin = db.scalar(select(AdminUser).where(AdminUser.username == "stage6-owner"))
        if admin:
            db.delete(admin)
            db.commit()
        admin = AdminUser(
            username="stage6-owner",
            password_hash=hash_password("Stage6-Secure-Password"),
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()

    session = TestClient(app)
    login = session.post(
        "/admin/login",
        json={"username": "stage6-owner", "password": "Stage6-Secure-Password"},
    )
    assert login.status_code == 200
    assert "dawit_admin_session" in login.cookies

    me = session.get("/admin/me")
    assert me.status_code == 200
    assert me.json()["username"] == "stage6-owner"

    logout = session.post("/admin/logout")
    assert logout.status_code == 200
    assert session.get("/admin/me").status_code == 401


def test_argon2_password_verification():
    digest = hash_password("strong-admin-password")
    assert digest.startswith("$argon2")
    assert verify_password(digest, "strong-admin-password")
    assert not verify_password(digest, "wrong-password")

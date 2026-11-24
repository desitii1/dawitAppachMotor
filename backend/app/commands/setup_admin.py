import argparse

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models.admin import AdminUser
from app.security.authentication import hash_password


def setup_admin(username: str | None = None, password: str | None = None) -> AdminUser:
    username = username or settings.admin_username
    password = password or settings.admin_password
    if not username or not password:
        raise RuntimeError("Provide ADMIN_USERNAME and ADMIN_PASSWORD")
    if len(password) < 8:
        raise RuntimeError("Admin password must be at least 8 characters")

    db = SessionLocal()
    try:
        admin = db.scalar(select(AdminUser).where(AdminUser.username == username))
        if admin:
            return admin
        admin = AdminUser(username=username, password_hash=hash_password(password))
        db.add(admin)
        db.commit()
        db.refresh(admin)
        return admin
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--username")
    parser.add_argument("--password")
    args = parser.parse_args()
    created = setup_admin(args.username, args.password)
    print(f"Admin account ready: {created.username}")

from datetime import datetime, timedelta, timezone
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, status
from sqlalchemy import select

from app.database import SessionLocal
from app.models.admin import AdminUser


password_hasher = PasswordHasher()
SESSION_COOKIE_NAME = "dawit_admin_session"
_failed_attempts: dict[str, list[datetime]] = {}
_attempt_lock = Lock()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def check_login_rate_limit(key: str) -> None:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=15)
    with _attempt_lock:
        attempts = [attempt for attempt in _failed_attempts.get(key, []) if attempt > window_start]
        _failed_attempts[key] = attempts
        if len(attempts) >= 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
            )


def record_failed_login(key: str) -> None:
    with _attempt_lock:
        _failed_attempts.setdefault(key, []).append(datetime.now(timezone.utc))


def clear_failed_login(key: str) -> None:
    with _attempt_lock:
        _failed_attempts.pop(key, None)


def get_current_admin(request: Request) -> AdminUser:
    raw_admin_id = getattr(request.state, "admin_id", None)
    if raw_admin_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")
    db = SessionLocal()
    try:
        admin = db.scalar(select(AdminUser).where(AdminUser.id == int(raw_admin_id)))
        if admin is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")
        db.expunge(admin)
        return admin
    finally:
        db.close()

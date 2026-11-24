from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.reservation import Reservation
from app.commands.setup_admin import setup_admin


client = TestClient(app)
setup_admin("stage3-test-owner", "Stage3-Secure-Password")
login = client.post("/admin/login", json={"username": "stage3-test-owner", "password": "Stage3-Secure-Password"})
assert login.status_code == 200


def create_test_lottery(name: str, start: int = 0, end: int = 4, limit: int = 3):
    response = client.post(
        "/lotteries",
        json={
            "name": name,
            "start_number": start,
            "end_number": end,
            "ticket_price": "100.00",
            "currency": "ETB",
            "reservation_duration_hours": 24,
            "max_numbers_per_customer": limit,
            "status": "ACTIVE",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_atomic_reservation_and_customer_limit():
    lottery = create_test_lottery("Stage 3 Limit Lottery", 0, 4, 3)
    payload = {
        "telegram_id": 900003,
        "telegram_username": "stage3",
        "full_name": "ዳዊት ተስቶ",
        "phone_number": "+251912345678",
        "lottery_id": lottery["id"],
    }

    first = client.post("/reservations", json={**payload, "numbers": ["0", "1"]})
    assert first.status_code == 201

    second = client.post("/reservations", json={**payload, "numbers": ["2"]})
    assert second.status_code == 201

    blocked = client.post("/reservations", json={**payload, "numbers": ["3"]})
    assert blocked.status_code == 422
    assert "can select only 0 more" not in blocked.json()["detail"]
    assert "3 numbers" in blocked.json()["detail"]


def test_entire_reservation_rejected_if_one_number_is_unavailable():
    lottery = create_test_lottery("Stage 3 Atomic Lottery", 10, 14, 5)
    first = client.post(
        "/reservations",
        json={
            "telegram_id": 900004,
            "full_name": "Customer One",
            "phone_number": "0912345678",
            "lottery_id": lottery["id"],
            "numbers": ["10"],
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/reservations",
        json={
            "telegram_id": 900005,
            "full_name": "Customer Two",
            "phone_number": "251912345678",
            "lottery_id": lottery["id"],
            "numbers": ["10", "11"],
        },
    )
    assert second.status_code == 409
    assert "10" in second.json()["detail"]

    tickets = client.get(
        f"/lotteries/{lottery['id']}/tickets",
        params={"search": "11"},
    ).json()
    assert tickets["items"][0]["status"] == "AVAILABLE"


def test_expiration_releases_numbers():
    lottery = create_test_lottery("Stage 3 Expiration Lottery", 20, 24, 5)
    created = client.post(
        "/reservations",
        json={
            "telegram_id": 900006,
            "full_name": "ዳዊት",
            "phone_number": "+251912345678",
            "lottery_id": lottery["id"],
            "numbers": ["20", "21"],
        },
    )
    assert created.status_code == 201

    db = SessionLocal()
    try:
        reservation = db.get(Reservation, created.json()["id"])
        reservation.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    expired = client.post("/reservations/expire")
    assert expired.status_code == 200
    assert expired.json()["released_ticket_count"] >= 2

    tickets = client.get(
        f"/lotteries/{lottery['id']}/tickets",
        params={"search": "20"},
    ).json()
    assert tickets["items"][0]["status"] == "AVAILABLE"


def test_concurrent_customers_cannot_reserve_the_same_number():
    lottery = create_test_lottery("Stage 3 Concurrency Lottery", 30, 34, 5)

    def reserve(customer_id: int):
        return client.post(
            "/reservations",
            json={
                "telegram_id": customer_id,
                "full_name": f"Customer {customer_id}",
                "phone_number": "0912345678",
                "lottery_id": lottery["id"],
                "numbers": ["30"],
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(reserve, [900007, 900008]))

    assert sorted(response.status_code for response in responses) == [201, 409]

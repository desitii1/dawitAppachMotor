from fastapi.testclient import TestClient

from app.main import app
from app.commands.setup_admin import setup_admin


client = TestClient(app)
setup_admin("stage2-test-owner", "Stage2-Secure-Password")
login = client.post("/admin/login", json={"username": "stage2-test-owner", "password": "Stage2-Secure-Password"})
assert login.status_code == 200


def test_create_and_browse_lottery_with_leading_zeroes():
    response = client.post(
        "/lotteries",
        json={
            "name": "Stage 2 Test Lottery",
            "start_number": 0,
            "end_number": 999,
            "ticket_price": "100.00",
            "currency": "ETB",
            "reservation_duration_hours": 24,
            "max_numbers_per_customer": 100,
            "status": "ACTIVE",
        },
    )
    assert response.status_code == 201
    lottery = response.json()

    page = client.get(
        f"/lotteries/{lottery['id']}/tickets",
        params={"page": 1, "page_size": 6},
    )
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 1000
    assert [item["number"] for item in body["items"]] == [
        "000",
        "001",
        "002",
        "003",
        "004",
        "005",
    ]
    assert all(item["status"] == "AVAILABLE" for item in body["items"])


def test_search_and_filter_lottery_tickets():
    lotteries = client.get("/lotteries").json()
    lottery = next(item for item in lotteries if item["name"] == "Stage 2 Test Lottery")

    search = client.get(
        f"/lotteries/{lottery['id']}/tickets",
        params={"search": "003", "status": "AVAILABLE"},
    )
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["number"] == "003"

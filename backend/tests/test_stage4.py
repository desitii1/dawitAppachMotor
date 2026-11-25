from types import SimpleNamespace

from app.bot.handlers.customer import get_or_create_customer, mask_phone
from app.bot.keyboards import ticket_page
from app.database import SessionLocal
from app.models.customer import Customer


def test_telegram_customer_identification():
    db = SessionLocal()
    try:
        db.query(Customer).filter(Customer.telegram_id == 940001).delete()
        db.commit()
    finally:
        db.close()

    first_id = get_or_create_customer(940001, "first_username")
    second_id = get_or_create_customer(940001, "updated_username")
    assert first_id == second_id

    db = SessionLocal()
    try:
        customer = db.get(Customer, first_id)
        assert customer.telegram_id == 940001
        assert customer.telegram_username == "updated_username"
    finally:
        db.close()


def test_public_phone_is_masked():
    assert mask_phone("0912345678") == "09123456xx"
    assert mask_phone("251912345678") == "09123456xx"


def test_ticket_page_uses_symbols_and_buy_action():
    markup = ticket_page(
        [
            SimpleNamespace(number="001", status="AVAILABLE"),
            SimpleNamespace(number="002", status="SOLD"),
            SimpleNamespace(number="003", status="RESERVED"),
        ],
        lottery_id=1,
        page=1,
        pages=1,
        selected={"001"},
    )
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert any(label.startswith("🟢 001") for label in labels)
    assert any(label.startswith("🔴 002") for label in labels)
    assert any(label.startswith("🟡 003") for label in labels)
    assert "🟩  BUY NOW  ·  1" in labels
    assert not any("AVAILABLE" in label or "SOLD" in label or "Review" in label for label in labels)

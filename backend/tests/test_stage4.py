from app.bot.handlers.customer import get_or_create_customer, mask_phone
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

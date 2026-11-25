import asyncio
import logging
import time
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models.broadcast import Broadcast, BroadcastDelivery
from app.models.customer import Customer


class BroadcastError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def create_broadcast(
    db: Session,
    *,
    message_text: str,
    customer_ids: list[int] | None = None,
) -> Broadcast:
    message_text = message_text.strip()
    if not message_text:
        raise BroadcastError("Broadcast message cannot be blank")

    if customer_ids:
        customers = db.scalars(
            select(Customer).where(Customer.id.in_(customer_ids))
        ).all()
        if len(customers) != len(set(customer_ids)):
            raise BroadcastError("One or more selected customers no longer exist", 404)
    else:
        customers = db.scalars(select(Customer)).all()
    if not customers:
        raise BroadcastError("No customers are available for this broadcast")

    broadcast = Broadcast(message_text=message_text, status="QUEUED")
    db.add(broadcast)
    db.flush()
    db.add_all(
        BroadcastDelivery(
            broadcast_id=broadcast.id,
            customer_id=customer.id,
            delivery_status="PENDING",
        )
        for customer in customers
    )
    db.commit()
    db.refresh(broadcast)
    return broadcast


async def _send_message(telegram_id: int, message_text: str) -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.send_message(telegram_id, message_text)
    finally:
        await bot.session.close()


def process_broadcast(db: Session, broadcast_id: int) -> Broadcast:
    broadcast = db.scalar(
        select(Broadcast).where(Broadcast.id == broadcast_id).with_for_update()
    )
    if broadcast is None:
        raise BroadcastError("Broadcast not found", 404)
    if broadcast.status == "COMPLETED":
        return broadcast

    broadcast.status = "PROCESSING"
    db.commit()

    deliveries = db.scalars(
        select(BroadcastDelivery)
        .where(
            BroadcastDelivery.broadcast_id == broadcast_id,
            BroadcastDelivery.delivery_status == "PENDING",
        )
        .order_by(BroadcastDelivery.id)
    ).all()

    for delivery in deliveries:
        customer = db.get(Customer, delivery.customer_id)
        try:
            if customer is None:
                raise RuntimeError("Customer no longer exists")
            asyncio.run(_send_message(customer.telegram_id, broadcast.message_text))
            delivery.delivery_status = "SENT"
            delivery.sent_at = datetime.now(timezone.utc)
            delivery.error_message = None
        except Exception as exc:
            logging.exception(
                "Broadcast delivery failed: broadcast_id=%s delivery_id=%s",
                broadcast_id,
                delivery.id,
            )
            delivery.delivery_status = "FAILED"
            delivery.error_message = str(exc)[:2000]
            delivery.sent_at = None
        db.commit()
        time.sleep(0.05)

    sent = db.scalar(
        select(BroadcastDelivery.id)
        .where(
            BroadcastDelivery.broadcast_id == broadcast_id,
            BroadcastDelivery.delivery_status == "SENT",
        )
        .limit(1)
    )
    broadcast.status = "COMPLETED" if sent is not None else "FAILED"
    broadcast.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(broadcast)
    return broadcast


def retry_failed_deliveries(db: Session, broadcast_id: int) -> Broadcast:
    broadcast = db.scalar(
        select(Broadcast).where(Broadcast.id == broadcast_id).with_for_update()
    )
    if broadcast is None:
        raise BroadcastError("Broadcast not found", 404)
    if broadcast.status == "PROCESSING":
        raise BroadcastError("This broadcast is already being processed", 409)

    result = db.execute(
        update(BroadcastDelivery)
        .where(
            BroadcastDelivery.broadcast_id == broadcast_id,
            BroadcastDelivery.delivery_status == "FAILED",
        )
        .values(
            delivery_status="PENDING",
            error_message=None,
            sent_at=None,
        )
    )
    if result.rowcount == 0:
        raise BroadcastError("This broadcast has no failed deliveries to retry")

    broadcast.status = "QUEUED"
    broadcast.completed_at = None
    db.commit()
    db.refresh(broadcast)
    return broadcast

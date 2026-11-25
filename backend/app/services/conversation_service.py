import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.conversation_message import ConversationMessage
from app.models.customer import Customer


async def _send_telegram_message(telegram_id: int, message_text: str) -> int:
    bot = Bot(token=settings.telegram_bot_token)
    try:
        message = await bot.send_message(telegram_id, message_text)
        return message.message_id
    finally:
        await bot.session.close()


def send_customer_message(
    db: Session,
    *,
    customer: Customer,
    admin_user_id: int,
    message_text: str,
) -> ConversationMessage:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    telegram_message_id = asyncio.run(
        _send_telegram_message(customer.telegram_id, message_text)
    )
    message = ConversationMessage(
        customer_id=customer.id,
        admin_user_id=admin_user_id,
        direction="OUTBOUND",
        message_text=message_text,
        telegram_message_id=telegram_message_id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message

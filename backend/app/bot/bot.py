import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers.customer import router
from app.config import settings


async def run() -> None:
    if not settings.telegram_bot_token:
        logging.info("TELEGRAM_BOT_TOKEN is not configured; Telegram bot polling will not start")
        return

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())

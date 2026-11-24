import asyncio
import logging

from app.database import SessionLocal
from app.services.reservation_service import expire_reservations


async def expiration_loop(interval_seconds: int = 300) -> None:
    logging.info("Starting reservation expiration worker")
    while True:
        db = SessionLocal()
        try:
            released = expire_reservations(db)
            if released:
                logging.info("Released %d expired reservation tickets", released)
        finally:
            db.close()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(expiration_loop())

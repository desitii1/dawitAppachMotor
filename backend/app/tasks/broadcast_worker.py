import logging
import time

from sqlalchemy import or_, select

from app.database import SessionLocal
from app.models.broadcast import Broadcast
from app.services.broadcast_service import BroadcastError, process_broadcast


def broadcast_loop(interval_seconds: int = 3) -> None:
    logging.info("Starting Telegram broadcast worker")
    while True:
        db = SessionLocal()
        try:
            broadcast_id = db.scalar(
                select(Broadcast.id)
                .where(Broadcast.status.in_(("QUEUED", "PROCESSING")))
                .order_by(Broadcast.created_at, Broadcast.id)
                .limit(1)
            )
            if broadcast_id is not None:
                try:
                    process_broadcast(db, broadcast_id)
                except BroadcastError:
                    logging.exception("Could not process broadcast id=%s", broadcast_id)
        except Exception:
            db.rollback()
            logging.exception("Broadcast worker iteration failed")
        finally:
            db.close()
        time.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    broadcast_loop()

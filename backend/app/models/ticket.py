from datetime import datetime
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("lottery_id", "number", name="uq_ticket_lottery_number"),
        CheckConstraint("status IN ('AVAILABLE','RESERVED','SOLD')", name="ck_ticket_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lottery_id: Mapped[int] = mapped_column(ForeignKey("lotteries.id", ondelete="RESTRICT"), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="AVAILABLE", index=True)
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

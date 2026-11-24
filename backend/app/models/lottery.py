from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Lottery(Base):
    __tablename__ = "lotteries"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','ACTIVE','PAUSED','CLOSED')", name="ck_lottery_status"),
        CheckConstraint("start_number >= 0", name="ck_lottery_start_nonnegative"),
        CheckConstraint("end_number >= start_number", name="ck_lottery_range"),
        CheckConstraint("ticket_price >= 0", name="ck_lottery_price"),
        CheckConstraint("reservation_duration_hours > 0", name="ck_lottery_duration"),
        CheckConstraint("max_numbers_per_customer > 0", name="ck_lottery_limit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_number: Mapped[int] = mapped_column(Integer, nullable=False)
    end_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ticket_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("100.00"))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="ETB")
    reservation_duration_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    max_numbers_per_customer: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

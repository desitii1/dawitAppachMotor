from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import AdminUser
from app.models.customer import Customer
from app.models.lottery import Lottery
from app.models.payment import Payment
from app.models.ticket import Ticket
from app.security.authentication import get_current_admin


router = APIRouter(prefix="/admin/reports", tags=["reports"])


@router.get("")
def sales_report(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    approved_payments = db.scalar(
        select(func.count()).select_from(Payment).where(Payment.status == "APPROVED")
    ) or 0
    confirmed_revenue = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "APPROVED")
    ) or 0
    pending_payments = db.scalar(
        select(func.count()).select_from(Payment).where(Payment.status == "PAYMENT_SUBMITTED")
    ) or 0

    lottery_totals = []
    lotteries = db.scalars(select(Lottery).order_by(Lottery.created_at.desc())).all()
    for lottery in lotteries:
        sold = db.scalar(
            select(func.count()).select_from(Ticket).where(
                Ticket.lottery_id == lottery.id,
                Ticket.status == "SOLD",
            )
        ) or 0
        reserved = db.scalar(
            select(func.count()).select_from(Ticket).where(
                Ticket.lottery_id == lottery.id,
                Ticket.status == "RESERVED",
            )
        ) or 0
        available = db.scalar(
            select(func.count()).select_from(Ticket).where(
                Ticket.lottery_id == lottery.id,
                Ticket.status == "AVAILABLE",
            )
        ) or 0
        lottery_totals.append({
            "lottery_id": lottery.id,
            "name": lottery.name,
            "status": lottery.status,
            "sold": sold,
            "reserved": reserved,
            "available": available,
            "confirmed_revenue": float(sold) * float(lottery.ticket_price),
        })

    return {
        "approved_payments": approved_payments,
        "pending_payments": pending_payments,
        "confirmed_revenue": float(confirmed_revenue),
        "total_customers": db.scalar(select(func.count()).select_from(Customer)) or 0,
        "lotteries": lottery_totals,
    }

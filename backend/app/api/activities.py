from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity import ActivityLog
from app.models.admin import AdminUser
from app.models.customer import Customer
from app.security.authentication import get_current_admin


router = APIRouter(prefix="/admin/activities", tags=["activities"])


@router.get("")
def list_activities(
    search: str | None = None,
    activity_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    query = select(
        ActivityLog,
        Customer.full_name,
        Customer.phone_number,
        Customer.telegram_id,
    ).outerjoin(
        Customer, Customer.id == ActivityLog.customer_id
    )
    if activity_type:
        query = query.where(ActivityLog.activity_type == activity_type)
    if search:
        query = query.where(
            Customer.full_name.ilike(f"%{search}%")
            | Customer.phone_number.contains(search)
        )
    activities = db.execute(
        query.order_by(ActivityLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [
        {
            "id": activity.id,
            "customer_id": activity.customer_id,
            "customer_name": customer_name,
            "phone_number": phone_number,
            "telegram_id": telegram_id,
            "admin_user_id": activity.admin_user_id,
            "activity_type": activity.activity_type,
            "description": activity.description,
            "created_at": activity.created_at,
        }
        for activity, customer_name, phone_number, telegram_id in activities
    ]

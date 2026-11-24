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
    query = select(ActivityLog)
    if activity_type:
        query = query.where(ActivityLog.activity_type == activity_type)
    if search:
        query = query.join(Customer, Customer.id == ActivityLog.customer_id, isouter=True).where(
            Customer.full_name.ilike(f"%{search}%")
            | Customer.phone_number.contains(search)
        )
    activities = db.scalars(
        query.order_by(ActivityLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [
        {
            "id": activity.id,
            "customer_id": activity.customer_id,
            "customer_name": db.get(Customer, activity.customer_id).full_name
            if activity.customer_id and db.get(Customer, activity.customer_id)
            else None,
            "telegram_id": db.get(Customer, activity.customer_id).telegram_id
            if activity.customer_id and db.get(Customer, activity.customer_id)
            else None,
            "admin_user_id": activity.admin_user_id,
            "activity_type": activity.activity_type,
            "description": activity.description,
            "created_at": activity.created_at,
        }
        for activity in activities
    ]

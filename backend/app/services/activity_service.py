from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog


def record_activity(
    db: Session,
    *,
    activity_type: str,
    description: str,
    customer_id: int | None = None,
    admin_user_id: int | None = None,
) -> ActivityLog:
    activity = ActivityLog(
        customer_id=customer_id,
        admin_user_id=admin_user_id,
        activity_type=activity_type,
        description=description,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity

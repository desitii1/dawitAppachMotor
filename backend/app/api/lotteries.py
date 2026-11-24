from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.lottery import (
    LotteryCreate,
    LotteryResponse,
    LotteryUpdate,
    TicketPageResponse,
)
from app.services import lottery_service
from app.models.admin import AdminUser
from app.security.authentication import get_current_admin


router = APIRouter(prefix="/lotteries", tags=["lotteries"])


@router.post("", response_model=LotteryResponse, status_code=status.HTTP_201_CREATED)
def create_lottery(payload: LotteryCreate, db: Session = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    try:
        return lottery_service.create_lottery(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[LotteryResponse])
def list_lotteries(db: Session = Depends(get_db)):
    return lottery_service.list_lotteries(db)


@router.get("/{lottery_id}", response_model=LotteryResponse)
def get_lottery(lottery_id: int, db: Session = Depends(get_db)):
    lottery = lottery_service.get_lottery(db, lottery_id)
    if lottery is None:
        raise HTTPException(status_code=404, detail="Lottery not found")
    return lottery


@router.patch("/{lottery_id}", response_model=LotteryResponse)
def update_lottery(lottery_id: int, payload: LotteryUpdate, db: Session = Depends(get_db), admin: AdminUser = Depends(get_current_admin)):
    lottery = lottery_service.get_lottery(db, lottery_id)
    if lottery is None:
        raise HTTPException(status_code=404, detail="Lottery not found")
    try:
        return lottery_service.update_lottery(
            db,
            lottery,
            payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{lottery_id}/tickets", response_model=TicketPageResponse)
def list_tickets(
    lottery_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    if lottery_service.get_lottery(db, lottery_id) is None:
        raise HTTPException(status_code=404, detail="Lottery not found")
    try:
        items, total, pages = lottery_service.list_tickets(
            db,
            lottery_id,
            page,
            page_size,
            status,
            search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }

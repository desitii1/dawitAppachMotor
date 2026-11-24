from math import ceil

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.ticket import Ticket


MAX_GENERATED_NUMBERS = 1_000_000


def format_lottery_number(value: int, start: int, end: int) -> str:
    width = max(len(str(start)), len(str(end)))
    return f"{value:0{width}d}"


def create_lottery(db: Session, values: dict) -> Lottery:
    start = values["start_number"]
    end = values["end_number"]
    count = end - start + 1
    if count > MAX_GENERATED_NUMBERS:
        raise ValueError("Lottery range cannot contain more than 1,000,000 numbers")
    if end < start:
        raise ValueError("end_number must be greater than or equal to start_number")

    lottery = Lottery(**values)
    db.add(lottery)
    db.flush()

    try:
        db.add_all(
            Ticket(
                lottery_id=lottery.id,
                number=format_lottery_number(value, start, end),
                status="AVAILABLE",
            )
            for value in range(start, end + 1)
        )
        db.commit()
        db.refresh(lottery)
        return lottery
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Lottery number range conflicts with an existing lottery") from exc


def update_lottery(db: Session, lottery: Lottery, values: dict) -> Lottery:
    start = values.get("start_number", lottery.start_number)
    end = values.get("end_number", lottery.end_number)
    if end < start:
        raise ValueError("end_number must be greater than or equal to start_number")

    has_conflicting_activity = (
        db.scalar(select(func.count()).select_from(Ticket).where(Ticket.lottery_id == lottery.id, Ticket.status != "AVAILABLE"))
        or 0
    )
    if (start != lottery.start_number or end != lottery.end_number) and has_conflicting_activity:
        raise ValueError("Number range cannot change while tickets are reserved or sold")

    if start != lottery.start_number or end != lottery.end_number:
        count = end - start + 1
        if count > MAX_GENERATED_NUMBERS:
            raise ValueError("Lottery range cannot contain more than 1,000,000 numbers")
        db.query(Ticket).filter(Ticket.lottery_id == lottery.id).delete(synchronize_session=False)
        for key, value in values.items():
            setattr(lottery, key, value)
        db.flush()
        db.add_all(
            Ticket(
                lottery_id=lottery.id,
                number=format_lottery_number(value, start, end),
                status="AVAILABLE",
            )
            for value in range(start, end + 1)
        )
    else:
        for key, value in values.items():
            setattr(lottery, key, value)

    db.commit()
    db.refresh(lottery)
    return lottery


def list_lotteries(db: Session) -> list[Lottery]:
    return list(db.scalars(select(Lottery).order_by(Lottery.created_at.desc(), Lottery.id.desc())))


def get_lottery(db: Session, lottery_id: int) -> Lottery | None:
    return db.get(Lottery, lottery_id)


def list_tickets(
    db: Session,
    lottery_id: int,
    page: int,
    page_size: int,
    status: str | None,
    search: str | None,
) -> tuple[list[Ticket], int, int]:
    query = select(Ticket).where(Ticket.lottery_id == lottery_id)
    count_query = select(func.count()).select_from(Ticket).where(Ticket.lottery_id == lottery_id)

    if status:
        status = status.upper()
        if status not in {"AVAILABLE", "RESERVED", "SOLD"}:
            raise ValueError("status must be AVAILABLE, RESERVED, or SOLD")
        query = query.where(Ticket.status == status)
        count_query = count_query.where(Ticket.status == status)

    if search:
        normalized = search.strip()
        query = query.where(Ticket.number.contains(normalized))
        count_query = count_query.where(Ticket.number.contains(normalized))

    total = db.scalar(count_query) or 0
    offset = (page - 1) * page_size
    items = list(db.scalars(query.order_by(Ticket.number.asc()).offset(offset).limit(page_size)))
    pages = ceil(total / page_size) if total else 0
    return items, total, pages

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from io import BytesIO

from app.bot.keyboards import lottery_menu, main_menu, ticket_page
from app.bot.states import CustomerFlow
from app.database import SessionLocal
from app.models.customer import Customer
from app.models.lottery import Lottery
from app.models.reservation import Reservation
from app.models.reservation import ReservationItem
from app.models.ticket import Ticket
from app.models.payment import Payment
from app.services.payment_service import PaymentSubmissionError, submit_payment_screenshot
from app.config import settings
from app.services.activity_service import record_activity
from app.services.lottery_service import list_lotteries, list_tickets
from app.services.reservation_service import ReservationError, create_reservation


router = Router()


def get_or_create_customer(telegram_id: int, username: str | None) -> int:
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.telegram_id == telegram_id).one_or_none()
        if customer is None:
            customer = Customer(telegram_id=telegram_id, telegram_username=username)
            db.add(customer)
            db.commit()
            db.refresh(customer)
        else:
            customer.telegram_username = username
            db.commit()
        return customer.id
    finally:
        db.close()


def mask_phone(phone: str | None) -> str:
    if not phone:
        return ""
    compact = phone.strip().replace(" ", "").replace("-", "")
    if compact.startswith("+251"):
        compact = "0" + compact[4:]
    elif compact.startswith("251"):
        compact = "0" + compact[3:]
    digits = compact[-10:] if len(compact) >= 10 else compact
    return digits[:-2] + "xx"


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    customer_id = get_or_create_customer(message.from_user.id, message.from_user.username)
    db = SessionLocal()
    try:
        record_activity(
            db,
            customer_id=customer_id,
            activity_type="BOT_STARTED",
            description="Customer started the Telegram bot",
        )
    finally:
        db.close()
    await message.answer(
        "Welcome to DawitAppachMotor. Choose an option:",
        reply_markup=main_menu(),
    )


@router.message(F.text.in_({"View Lottery Numbers", "Select Numbers"}))
async def choose_lottery(message: Message, state: FSMContext):
    await state.clear()
    db = SessionLocal()
    try:
        lotteries = [item for item in list_lotteries(db) if item.status == "ACTIVE"]
    finally:
        db.close()
    if not lotteries:
        await message.answer("No active lottery is available.")
        return
    await message.answer("Choose a lottery:", reply_markup=lottery_menu(lotteries))


@router.callback_query(F.data.startswith("lottery:"))
async def open_lottery(callback: CallbackQuery, state: FSMContext):
    lottery_id = int(callback.data.split(":", 1)[1])
    await state.clear()
    await state.update_data(lottery_id=lottery_id, selected=[])
    await show_page(callback, state, lottery_id, 1)
    await callback.answer()


async def show_page(
    callback: CallbackQuery,
    state: FSMContext,
    lottery_id: int,
    page: int,
    search: str | None = None,
):
    db = SessionLocal()
    try:
        items, total, pages = list_tickets(db, lottery_id, page, 20, None, search)
    finally:
        db.close()
    state_data = await state.get_data()
    selected = set(state_data.get("selected", []))
    text = f"Lottery numbers - Page {page}/{max(pages, 1)}"
    if search:
        text += f"\nSearch: {search}"
    if not items:
        text += "\nNo numbers found."
    else:
        lines = []
        for item in items:
            if item.status == "SOLD":
                db = SessionLocal()
                try:
                    customer = db.get(Customer, item.customer_id)
                finally:
                    db.close()
                detail = f"Sold ({mask_phone(customer.phone_number) if customer else 'xxxxxxxxxx'})"
            elif item.status == "RESERVED":
                detail = "Temporarily unavailable"
            else:
                detail = "Available"
            lines.append(f"{item.number}: {detail}")
        text += "\n" + "\n".join(lines)
    await callback.message.edit_text(
        text,
        reply_markup=ticket_page(items, lottery_id, page, pages, selected),
    )


@router.callback_query(F.data.startswith("page:"))
async def paginate(callback: CallbackQuery, state: FSMContext):
    _, lottery_id, page = callback.data.split(":")
    await show_page(callback, state, int(lottery_id), int(page))
    await callback.answer()


@router.callback_query(F.data.startswith("search:"))
async def start_search(callback: CallbackQuery, state: FSMContext):
    _, lottery_id = callback.data.split(":")
    await state.update_data(lottery_id=int(lottery_id))
    await state.set_state(CustomerFlow.searching)
    await callback.message.answer("Send the number to search for.")
    await callback.answer()


@router.message(CustomerFlow.searching)
async def search_number(message: Message, state: FSMContext):
    data = await state.get_data()
    lottery_id = data["lottery_id"]
    await state.set_state(CustomerFlow.selecting)
    db = SessionLocal()
    try:
        items, total, pages = list_tickets(db, lottery_id, 1, 20, None, message.text.strip())
    finally:
        db.close()
    if not items:
        await message.answer("No matching numbers found.")
        return
    selected = set(data.get("selected", []))
    text = "Search results:\n" + "\n".join(
        f"{item.number}: {'Sold' if item.status == 'SOLD' else 'Temporarily unavailable' if item.status == 'RESERVED' else 'Available'}"
        for item in items
    )
    await message.answer(text, reply_markup=ticket_page(items, lottery_id, 1, pages, selected))


@router.callback_query(F.data.startswith("ticket:"))
async def toggle_ticket(callback: CallbackQuery, state: FSMContext):
    _, lottery_id, number = callback.data.split(":")
    lottery_id = int(lottery_id)
    db = SessionLocal()
    try:
        lottery = db.get(Lottery, lottery_id)
        ticket = db.scalar(
            select(Ticket).where(Ticket.lottery_id == lottery_id, Ticket.number == number)
        )
    finally:
        db.close()
    if ticket is None or ticket.status != "AVAILABLE":
        await callback.answer("This number is no longer available.", show_alert=True)
        return

    data = await state.get_data()
    selected = list(data.get("selected", []))
    if number in selected:
        selected.remove(number)
    else:
        if len(selected) >= lottery.max_numbers_per_customer:
            await callback.answer(
                f"You can select a maximum of {lottery.max_numbers_per_customer} numbers.",
                show_alert=True,
            )
            return
        selected.append(number)
    await state.update_data(selected=selected)
    await show_page(callback, state, lottery_id, 1)
    await callback.answer("Selection updated.")


@router.callback_query(F.data.startswith("review:"))
async def review_selection(callback: CallbackQuery, state: FSMContext):
    _, lottery_id = callback.data.split(":")
    data = await state.get_data()
    selected = data.get("selected", [])
    if not selected:
        await callback.answer("Select at least one number.", show_alert=True)
        return
    db = SessionLocal()
    try:
        lottery = db.get(Lottery, int(lottery_id))
    finally:
        db.close()
    total = lottery.ticket_price * len(selected)
    await state.update_data(lottery_id=int(lottery_id))
    await state.set_state(CustomerFlow.collecting_name)
    await callback.message.answer(
        f"Selected numbers: {', '.join(selected)}\n"
        f"Ticket count: {len(selected)}\n"
        f"Price per ticket: {lottery.ticket_price} {lottery.currency}\n"
        f"Total: {total} {lottery.currency}\n\n"
        "Send your full name."
    )
    await callback.answer()


@router.message(CustomerFlow.collecting_name)
async def collect_name(message: Message, state: FSMContext):
    full_name = " ".join(message.text.split())
    if not full_name:
        await message.answer("Please send a valid full name.")
        return
    await state.update_data(full_name=full_name)
    await state.set_state(CustomerFlow.collecting_phone)
    await message.answer("Send your Ethiopian phone number (09XXXXXXXX, +2519XXXXXXXX, or 2519XXXXXXXX).")


@router.message(CustomerFlow.collecting_phone)
async def collect_phone(message: Message, state: FSMContext):
    await state.update_data(phone_number=message.text.strip())
    await state.set_state(CustomerFlow.confirming)
    data = await state.get_data()
    db = SessionLocal()
    try:
        lottery = db.get(Lottery, data["lottery_id"])
    finally:
        db.close()
    selected = data["selected"]
    total = lottery.ticket_price * len(selected)
    await message.answer(
        f"Confirm reservation\n\n"
        f"Customer: {data['full_name']}\n"
        f"Phone: {message.text.strip()}\n"
        f"Numbers: {', '.join(selected)}\n"
        f"Ticket count: {len(selected)}\n"
        f"Price: {lottery.ticket_price} {lottery.currency}\n"
        f"Total: {total} {lottery.currency}\n"
        f"Expires in: {lottery.reservation_duration_hours} hours\n\n"
        "Reply CONFIRM to reserve these numbers.",
    )


@router.message(CustomerFlow.confirming, F.text.casefold() == "confirm")
async def confirm_reservation(message: Message, state: FSMContext):
    data = await state.get_data()
    db = SessionLocal()
    try:
        reservation = create_reservation(
            db,
            telegram_id=message.from_user.id,
            telegram_username=message.from_user.username,
            full_name=data["full_name"],
            phone_number=data["phone_number"],
            lottery_id=data["lottery_id"],
            numbers=data["selected"],
        )
    except ReservationError as exc:
        await message.answer(exc.message)
        return
    finally:
        db.close()

    await state.clear()
    await message.answer(
        f"Reservation: {reservation.reference}\n"
        f"Numbers: {', '.join(data['selected'])}\n"
        f"Ticket count: {len(data['selected'])}\n"
        f"Total: {reservation.total_amount} ETB\n"
        f"Expires: {reservation.expires_at.isoformat()}",
    )


@router.message(F.text == "My Reservations")
async def my_reservations(message: Message):
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.telegram_id == message.from_user.id))
        if customer is None:
            reservations = []
        else:
            reservations = db.scalars(
                select(Reservation).where(
                    Reservation.customer_id == customer.id,
                    Reservation.status.in_(("AWAITING_PAYMENT", "PAYMENT_SUBMITTED")),
                ).order_by(Reservation.created_at.desc())
            ).all()
            result = []
            for reservation in reservations:
                numbers = db.scalars(
                    select(Ticket.number)
                    .join(ReservationItem, ReservationItem.ticket_id == Ticket.id)
                    .where(ReservationItem.reservation_id == reservation.id)
                    .order_by(Ticket.number)
                ).all()
                result.append((reservation, numbers))
    finally:
        db.close()
    if not reservations:
        await message.answer("You have no active reservations.")
        return
    await message.answer(
        "\n\n".join(
            f"{reservation.reference}: {', '.join(numbers)}\n"
            f"Status: {reservation.status}\nExpires: {reservation.expires_at.isoformat()}"
            for reservation, numbers in result
        )
    )


@router.message(F.text == "My Purchased Numbers")
async def my_purchased_numbers(message: Message):
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.telegram_id == message.from_user.id))
        numbers = [] if customer is None else db.scalars(
            select(Ticket.number).where(Ticket.customer_id == customer.id, Ticket.status == "SOLD").order_by(Ticket.number)
        ).all()
    finally:
        db.close()
    await message.answer(
        "Your purchased numbers:\n" + ", ".join(numbers)
        if numbers else "You have no purchased numbers."
    )


async def submit_telegram_screenshot(
    message: Message,
    file_id: str,
    original_filename: str,
    content_type: str,
) -> str:
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.telegram_id == message.from_user.id))
        if customer is None:
            return "Send /start before uploading a payment screenshot."
        reservation = db.scalar(
            select(Reservation)
            .where(
                Reservation.customer_id == customer.id,
                Reservation.status.in_(("AWAITING_PAYMENT", "PAYMENT_SUBMITTED")),
            )
            .order_by(Reservation.created_at.desc())
        )
        if reservation is None:
            return "No active reservation was found for your account."

        telegram_file = await message.bot.get_file(file_id)
        buffer = BytesIO()
        await message.bot.download_file(telegram_file.file_path, destination=buffer)
        try:
            submit_payment_screenshot(
                db,
                reservation_reference=reservation.reference,
                telegram_id=message.from_user.id,
                content=buffer.getvalue(),
                content_type=content_type,
                original_filename=original_filename,
                attachment_root=settings.attachment_root,
            )
        except PaymentSubmissionError as exc:
            return exc.message
        return f"Payment screenshot submitted for reservation {reservation.reference}. It awaits administrator approval."
    finally:
        db.close()


@router.message(F.photo)
async def submit_photo(message: Message):
    photo = message.photo[-1]
    response = await submit_telegram_screenshot(
        message,
        photo.file_id,
        f"telegram-photo-{photo.file_unique_id}.jpg",
        "image/jpeg",
    )
    await message.answer(response)


@router.message(F.document)
async def submit_document(message: Message):
    document = message.document
    content_type = document.mime_type or "application/octet-stream"
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        await message.answer("Please send the payment screenshot as a JPEG, PNG, or WebP image.")
        return
    response = await submit_telegram_screenshot(
        message,
        document.file_id,
        document.file_name or f"telegram-document-{document.file_unique_id}",
        content_type,
    )
    await message.answer(response)


@router.message(F.text == "Payment Instructions")
async def payment_instructions(message: Message):
    await message.answer("Payment instructions are currently being configured by the lottery administrator.")


@router.message(F.text == "Contact Support")
async def contact_support(message: Message):
    await message.answer("Please contact the lottery administrator through the support channel published by the operator.")

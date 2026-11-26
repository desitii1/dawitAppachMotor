from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from datetime import datetime, timezone
from sqlalchemy import select
from io import BytesIO

from app.bot.keyboards import lottery_menu, main_menu, ticket_page
from app.bot.states import CustomerFlow
from app.database import SessionLocal
from app.models.activity import ActivityLog
from app.models.customer import Customer
from app.models.conversation_message import ConversationMessage
from app.models.lottery import Lottery
from app.models.reservation import Reservation
from app.models.reservation import ReservationItem
from app.models.ticket import Ticket
from app.models.payment import Payment
from app.services.payment_service import PaymentSubmissionError, submit_payment_screenshot
from app.config import settings
from app.services.lottery_service import list_lotteries, list_tickets
from app.services.reservation_service import (
    ReservationError,
    create_reservation,
    normalize_phone_number,
)


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


def record_bot_activity(telegram_id: int, activity_type: str, description: str) -> None:
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
        if customer is None:
            return
        customer.last_activity_at = datetime.now(timezone.utc)
        db.add(
            ActivityLog(
                customer_id=customer.id,
                activity_type=activity_type,
                description=description,
            )
        )
        db.commit()
    finally:
        db.close()


def store_inbound_message(telegram_id: int, message_id: int, message_text: str) -> bool:
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.telegram_id == telegram_id))
        if customer is None:
            return False
        customer.last_activity_at = datetime.now(timezone.utc)
        db.add(
            ConversationMessage(
                customer_id=customer.id,
                direction="INBOUND",
                message_text=message_text,
                telegram_message_id=message_id,
            )
        )
        db.add(
            ActivityLog(
                customer_id=customer.id,
                activity_type="CUSTOMER_SUPPORT_MESSAGE",
                description="Customer sent a message to support",
            )
        )
        db.commit()
        return True
    finally:
        db.close()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    get_or_create_customer(message.from_user.id, message.from_user.username)
    record_bot_activity(
        message.from_user.id,
        "BOT_STARTED",
        "Customer started the Telegram bot",
    )
    await message.answer(
        "Welcome to DawitAppachMotor. Choose a lottery or use the menu:",
        reply_markup=main_menu(),
    )
    await send_lottery_list(message)


async def send_lottery_list(message: Message):
    db = SessionLocal()
    try:
        lotteries = [item for item in list_lotteries(db) if item.status == "ACTIVE"]
    finally:
        db.close()
    if lotteries:
        await message.answer("Available lotteries:", reply_markup=lottery_menu(lotteries))
    else:
        await message.answer("There are no active lotteries right now.")


@router.message(F.text.in_({"View Lottery Numbers", "Select Numbers"}))
async def choose_lottery(message: Message, state: FSMContext):
    await state.clear()
    await send_lottery_list(message)


@router.callback_query(F.data.startswith("lottery:"))
async def open_lottery(callback: CallbackQuery, state: FSMContext):
    lottery_id = int(callback.data.split(":", 1)[1])
    await state.clear()
    await state.update_data(lottery_id=lottery_id, selected=[])
    record_bot_activity(
        callback.from_user.id,
        "LOTTERY_OPENED",
        f"Customer opened lottery {lottery_id}",
    )
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
                detail = f"🔴 {mask_phone(customer.phone_number) if customer else 'xxxxxxxxxx'}"
            elif item.status == "RESERVED":
                detail = "🟡"
            else:
                detail = "🟢"
            lines.append(f"{detail} {item.number}")
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
    record_bot_activity(
        message.from_user.id,
        "NUMBER_SEARCHED",
        f"Customer searched lottery {lottery_id} for {message.text.strip()}",
    )
    if not items:
        await message.answer("No matching numbers found.")
        return
    selected = set(data.get("selected", []))
    text = "Search results:\n" + "\n".join(
        f"{'🔴' if item.status == 'SOLD' else '🟡' if item.status == 'RESERVED' else '🟢'} {item.number}"
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
        action = "deselected"
    else:
        if len(selected) >= lottery.max_numbers_per_customer:
            await callback.answer(
                f"You can select a maximum of {lottery.max_numbers_per_customer} numbers.",
                show_alert=True,
            )
            return
        selected.append(number)
        action = "selected"
    await state.update_data(selected=selected)
    record_bot_activity(
        callback.from_user.id,
        "NUMBER_SELECTION_CHANGED",
        f"Customer {action} number {number} in lottery {lottery_id}",
    )
    await show_page(callback, state, lottery_id, 1)
    await callback.answer("Selection updated.")


@router.callback_query(F.data.startswith("buy:"))
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
        f"Review your numbers\n\n"
        f"Customer: {data['full_name']}\n"
        f"Phone: {message.text.strip()}\n"
        f"Numbers: {', '.join(selected)}\n"
        f"Ticket count: {len(selected)}\n"
        f"Price: {lottery.ticket_price} {lottery.currency}\n"
        f"Total: {total} {lottery.currency}\n"
        f"Expires in: {lottery.reservation_duration_hours} hours",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📨 Send", callback_data="send_reservation")]
            ]
        ),
    )


@router.callback_query(CustomerFlow.confirming, F.data == "send_reservation")
async def send_reservation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db = SessionLocal()
    try:
        reservation = create_reservation(
            db,
            telegram_id=callback.from_user.id,
            telegram_username=callback.from_user.username,
            full_name=data["full_name"],
            phone_number=data["phone_number"],
            lottery_id=data["lottery_id"],
            numbers=data["selected"],
        )
    except ReservationError as exc:
        await callback.answer(exc.message, show_alert=True)
        return
    finally:
        db.close()

    await state.clear()
    await callback.message.answer(
        f"Reservation sent for numbers: {', '.join(data['selected'])}\n"
        f"Total: {reservation.total_amount} ETB\n"
        "Upload your payment image now as a photo or supported image file."
    )
    await callback.answer()


@router.message(F.text == "My Reservations")
async def my_reservations(message: Message):
    record_bot_activity(
        message.from_user.id,
        "RESERVATIONS_VIEWED",
        "Customer viewed active reservations",
    )
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
    for reservation, numbers in result:
        await message.answer(
            f"Numbers: {', '.join(numbers)}\n"
            f"Status: {reservation.status.replace('_', ' ').title()}\n"
            f"Expires: {reservation.expires_at.astimezone().strftime('%Y-%m-%d %H:%M')}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Replace payment screenshot",
                            callback_data=f"replace_screenshot:{reservation.id}",
                        )
                    ]
                ]
            ),
        )


@router.message(F.text == "Edit My Details")
async def start_profile_edit(message: Message, state: FSMContext):
    await state.clear()
    db = SessionLocal()
    try:
        customer = db.scalar(
            select(Customer).where(Customer.telegram_id == message.from_user.id)
        )
        current_name = customer.full_name if customer else None
        current_phone = customer.phone_number if customer else None
    finally:
        db.close()
    if customer is None:
        await message.answer("Please send /start before editing your details.")
        return
    await message.answer(
        f"Current name: {current_name or 'not set'}\n"
        f"Current phone: {current_phone or 'not set'}\n\n"
        "Choose what you want to correct:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Edit name", callback_data="edit_profile:name"),
                    InlineKeyboardButton(text="Edit phone", callback_data="edit_profile:phone"),
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("edit_profile:"))
async def start_profile_field_edit(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    if field == "name":
        await state.set_state(CustomerFlow.editing_profile_name)
        await callback.message.answer("Send your corrected full name.")
    elif field == "phone":
        await state.set_state(CustomerFlow.editing_profile_phone)
        await callback.message.answer(
            "Send your corrected Ethiopian phone number "
            "(09XXXXXXXX, +2519XXXXXXXX, or 2519XXXXXXXX)."
        )
    else:
        await callback.answer("This edit option is not available.", show_alert=True)
        return
    await callback.answer()


@router.message(CustomerFlow.editing_profile_name, F.text)
async def collect_profile_name(message: Message, state: FSMContext):
    full_name = " ".join(message.text.split())
    if not full_name or len(full_name) > 255:
        await message.answer("Please send a name between 1 and 255 characters.")
        return
    db = SessionLocal()
    try:
        customer = db.scalar(
            select(Customer).where(Customer.telegram_id == message.from_user.id)
        )
        if customer is None:
            await state.clear()
            await message.answer("Please send /start before editing your details.")
            return
        customer.full_name = full_name
        customer.last_activity_at = datetime.now(timezone.utc)
        db.add(
            ActivityLog(
                customer_id=customer.id,
                activity_type="CUSTOMER_DETAILS_UPDATED",
                description="Customer corrected their name",
            )
        )
        db.commit()
    finally:
        db.close()
    await state.clear()
    await message.answer(f"Your name has been updated to {full_name}.", reply_markup=main_menu())


@router.message(CustomerFlow.editing_profile_phone, F.text)
async def collect_profile_phone(message: Message, state: FSMContext):
    try:
        phone_number = normalize_phone_number(message.text)
    except ReservationError as exc:
        await message.answer(exc.message)
        return

    db = SessionLocal()
    try:
        customer = db.scalar(
            select(Customer).where(Customer.telegram_id == message.from_user.id)
        )
        if customer is None:
            await state.clear()
            await message.answer("Please send /start before editing your details.")
            return
        customer.phone_number = phone_number
        customer.last_activity_at = datetime.now(timezone.utc)
        db.add(
            ActivityLog(
                customer_id=customer.id,
                activity_type="CUSTOMER_DETAILS_UPDATED",
                description="Customer corrected their phone number",
            )
        )
        db.commit()
    finally:
        db.close()
    await state.clear()
    await message.answer(
        f"Your phone number has been updated to {phone_number}.",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data.startswith("replace_screenshot:"))
async def start_screenshot_replacement(callback: CallbackQuery, state: FSMContext):
    reservation_id = int(callback.data.split(":", 1)[1])
    db = SessionLocal()
    try:
        customer = db.scalar(
            select(Customer).where(Customer.telegram_id == callback.from_user.id)
        )
        reservation = (
            db.scalar(
                select(Reservation).where(
                    Reservation.id == reservation_id,
                    Reservation.customer_id == customer.id,
                    Reservation.status.in_(("AWAITING_PAYMENT", "PAYMENT_SUBMITTED")),
                )
            )
            if customer
            else None
        )
        if reservation is None:
            await callback.answer(
                "This reservation can no longer accept a payment screenshot.",
                show_alert=True,
            )
            return
        numbers = db.scalars(
            select(Ticket.number)
            .join(ReservationItem, ReservationItem.ticket_id == Ticket.id)
            .where(ReservationItem.reservation_id == reservation.id)
            .order_by(Ticket.number)
        ).all()
    finally:
        db.close()
    await state.clear()
    await state.update_data(payment_reservation_id=reservation_id)
    await state.set_state(CustomerFlow.replacing_payment_screenshot)
    await callback.message.answer(
        f"Send the corrected payment screenshot for numbers {', '.join(numbers)} "
        "as a photo or JPEG, PNG, or WebP image document."
    )
    await callback.answer()


@router.message(F.text == "My Purchased Numbers")
async def my_purchased_numbers(message: Message):
    record_bot_activity(
        message.from_user.id,
        "PURCHASED_NUMBERS_VIEWED",
        "Customer viewed purchased numbers",
    )
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
    reservation_id: int | None = None,
) -> str:
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.telegram_id == message.from_user.id))
        if customer is None:
            return "Send /start before uploading a payment screenshot."
        reservation_query = select(Reservation).where(
            Reservation.customer_id == customer.id,
            Reservation.status.in_(("AWAITING_PAYMENT", "PAYMENT_SUBMITTED")),
        )
        if reservation_id is not None:
            reservation_query = reservation_query.where(Reservation.id == reservation_id)
        else:
            reservation_query = reservation_query.order_by(Reservation.created_at.desc())
        reservation = db.scalar(reservation_query)
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
                replace_existing=reservation_id is not None,
            )
        except PaymentSubmissionError as exc:
            return exc.message
        numbers = db.scalars(
            select(Ticket.number)
            .join(ReservationItem, ReservationItem.ticket_id == Ticket.id)
            .where(ReservationItem.reservation_id == reservation.id)
            .order_by(Ticket.number)
        ).all()
        action = "replaced" if reservation_id is not None else "received"
        return f"Payment screenshot {action} for {', '.join(numbers)}. It is awaiting administrator approval."
    finally:
        db.close()


@router.message(F.photo)
async def submit_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]
    data = await state.get_data()
    reservation_id = (
        data.get("payment_reservation_id")
        if await state.get_state() == CustomerFlow.replacing_payment_screenshot.state
        else None
    )
    response = await submit_telegram_screenshot(
        message,
        photo.file_id,
        f"telegram-photo-{photo.file_unique_id}.jpg",
        "image/jpeg",
        reservation_id=reservation_id,
    )
    if reservation_id is not None and response.startswith("Payment screenshot replaced"):
        await state.clear()
    await message.answer(response)


@router.message(F.document)
async def submit_document(message: Message, state: FSMContext):
    document = message.document
    content_type = document.mime_type or "application/octet-stream"
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        await message.answer("Please send the payment screenshot as a JPEG, PNG, or WebP image.")
        return
    data = await state.get_data()
    reservation_id = (
        data.get("payment_reservation_id")
        if await state.get_state() == CustomerFlow.replacing_payment_screenshot.state
        else None
    )
    response = await submit_telegram_screenshot(
        message,
        document.file_id,
        document.file_name or f"telegram-document-{document.file_unique_id}",
        content_type,
        reservation_id=reservation_id,
    )
    if reservation_id is not None and response.startswith("Payment screenshot replaced"):
        await state.clear()
    await message.answer(response)


@router.message(CustomerFlow.replacing_payment_screenshot, F.text)
async def prompt_for_replacement_image(message: Message):
    await message.answer(
        "Please send the corrected screenshot as a photo or JPEG, PNG, or WebP image document."
    )


@router.message(F.text == "Payment Instructions")
async def payment_instructions(message: Message):
    record_bot_activity(
        message.from_user.id,
        "PAYMENT_INSTRUCTIONS_VIEWED",
        "Customer viewed payment instructions",
    )
    await message.answer("Payment instructions are currently being configured by the lottery administrator.")


@router.message(F.text == "Contact Support")
async def contact_support(message: Message, state: FSMContext):
    record_bot_activity(
        message.from_user.id,
        "SUPPORT_OPENED",
        "Customer opened the support conversation",
    )
    await state.set_state(CustomerFlow.supporting)
    await message.answer("Write your message to the lottery administrator.")


@router.message(CustomerFlow.supporting, F.text)
async def save_support_message(message: Message, state: FSMContext):
    message_text = message.text.strip()
    if not message_text:
        await message.answer("Please type a message for the administrator.")
        return

    if not store_inbound_message(
        message.from_user.id,
        message.message_id,
        message_text,
    ):
        await state.clear()
        await message.answer("Please send /start before contacting support.")
        return

    await state.clear()
    await message.answer("Your message was sent to support. The administrator will reply here.")


@router.message(F.text & ~F.text.startswith("/"))
async def receive_customer_message(message: Message):
    message_text = message.text.strip()
    if not message_text:
        return
    if store_inbound_message(
        message.from_user.id,
        message.message_id,
        message_text,
    ):
        await message.answer("Your message was sent to support. The administrator will reply here.")

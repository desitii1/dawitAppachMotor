from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="View Lottery Numbers"), KeyboardButton(text="Select Numbers")],
            [KeyboardButton(text="My Reservations"), KeyboardButton(text="My Purchased Numbers")],
            [KeyboardButton(text="Payment Instructions"), KeyboardButton(text="Contact Support")],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def lottery_menu(lotteries: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lottery in lotteries:
        builder.row(
            InlineKeyboardButton(
                text=f"{lottery.name} ({lottery.status})",
                callback_data=f"lottery:{lottery.id}",
            )
        )
    return builder.as_markup()


def ticket_page(items: list, lottery_id: int, page: int, pages: int, selected: set[str] | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    selected = selected or set()
    for item in items:
        indicator = "SOLD" if item.status == "SOLD" else "RES" if item.status == "RESERVED" else "AVAILABLE"
        check = " [x]" if item.number in selected else ""
        builder.button(
            text=f"{item.number} - {indicator}{check}",
            callback_data=f"ticket:{lottery_id}:{item.number}",
        )
    builder.adjust(2)
    navigation = []
    if page > 1:
        navigation.append(InlineKeyboardButton(text="Previous", callback_data=f"page:{lottery_id}:{page - 1}"))
    navigation.append(InlineKeyboardButton(text="Search", callback_data=f"search:{lottery_id}"))
    if page < pages:
        navigation.append(InlineKeyboardButton(text="Next", callback_data=f"page:{lottery_id}:{page + 1}"))
    if navigation:
        builder.row(*navigation)
    if selected:
        builder.row(
            InlineKeyboardButton(text=f"Review {len(selected)} selected", callback_data=f"review:{lottery_id}")
        )
    return builder.as_markup()

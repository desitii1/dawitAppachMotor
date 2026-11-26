from aiogram.fsm.state import State, StatesGroup


class CustomerFlow(StatesGroup):
    searching = State()
    selecting = State()
    collecting_name = State()
    collecting_phone = State()
    confirming = State()
    editing_profile_name = State()
    editing_profile_phone = State()
    replacing_payment_screenshot = State()
    supporting = State()

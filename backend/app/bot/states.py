from aiogram.fsm.state import State, StatesGroup


class CustomerFlow(StatesGroup):
    searching = State()
    selecting = State()
    collecting_name = State()
    collecting_phone = State()
    confirming = State()
    supporting = State()

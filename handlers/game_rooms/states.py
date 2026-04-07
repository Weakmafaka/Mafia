from aiogram.fsm.state import State, StatesGroup

DEFAULT_ROOM_PLAYERS = 6


class RoomState(StatesGroup):
    waiting_create_room_name = State()
    waiting_create_chat_link = State()
    waiting_create_password = State()
    waiting_create_settings_name = State()
    waiting_create_settings_password = State()
    waiting_join_code = State()
    waiting_join_password = State()
    waiting_owner_room_name = State()
    waiting_owner_room_password = State()
    waiting_mafia_visit_text = State()
    waiting_mafia_team_text = State()

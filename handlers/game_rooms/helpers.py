from typing import Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from database.controllers.room import RoomSnapshot


def mask_password(password: str) -> str:
    if not password:
        return "-"
    return "*" * min(len(password), 12)


async def safe_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def clear_state_keep_menu_message(state: FSMContext) -> Optional[int]:
    data = await state.get_data()
    menu_message_id = data.get("menu_message_id")
    await state.clear()
    if menu_message_id:
        await state.update_data(menu_message_id=menu_message_id)
    return menu_message_id


async def get_menu_message_id(state: FSMContext) -> Optional[int]:
    data = await state.get_data()
    return data.get("menu_message_id")


def short_name(value: str) -> str:
    trimmed = value.strip()
    if len(trimmed) <= 28:
        return trimmed
    return "{}...".format(trimmed[:25])


def is_owner(snapshot: RoomSnapshot, tg_user_id: int) -> bool:
    return snapshot.owner_tg_user_id == tg_user_id


def viewer_ready(snapshot: RoomSnapshot, tg_user_id: int) -> bool:
    for player in snapshot.players:
        if player.tg_user_id == tg_user_id:
            return player.is_ready
    return False

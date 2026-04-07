from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from database.controllers.room import get_user_room_snapshot
from database.controllers.ui_state import set_menu_message_id
from handlers.game_rooms.helpers import clear_state_keep_menu_message
from handlers.game_rooms.views import render_game_menu, render_room_lobby

router = Router()


@router.callback_query(F.data == "menu_start_game")
async def callback_start_game(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await clear_state_keep_menu_message(state)
    await state.update_data(menu_message_id=query.message.message_id)
    await set_menu_message_id(query.from_user.id, query.message.message_id)

    snapshot = await get_user_room_snapshot(query.from_user.id)
    if snapshot is not None:
        await render_room_lobby(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            viewer_tg_user_id=query.from_user.id,
            snapshot=snapshot,
            prefix="У тебя уже есть активная комната.",
        )
        return

    await render_game_menu(chat_id=query.message.chat.id, message_id=query.message.message_id)


@router.callback_query(F.data == "room_back_to_start")
async def callback_back_to_start_game(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await clear_state_keep_menu_message(state)
    await state.update_data(menu_message_id=query.message.message_id)
    await set_menu_message_id(query.from_user.id, query.message.message_id)
    await render_game_menu(chat_id=query.message.chat.id, message_id=query.message.message_id)


@router.callback_query(F.data == "room_noop")
async def callback_room_noop(query: CallbackQuery) -> None:
    await query.answer()


@router.callback_query(F.data == "room_roles_stub")
async def callback_room_roles_stub(query: CallbackQuery) -> None:
    await query.answer("Логика ролей будет добавлена позже.")


@router.callback_query(F.data == "create_game_settings_stub")
async def callback_create_game_settings_stub(query: CallbackQuery) -> None:
    await query.answer("Настройки игры откроются после создания комнаты.", show_alert=True)


@router.callback_query(F.data == "game_join_public_disabled")
async def callback_game_join_public_disabled(query: CallbackQuery) -> None:
    await query.answer("Публичные комнаты пока недоступны.", show_alert=True)


@router.callback_query(F.data == "create_visibility_public_disabled")
async def callback_create_visibility_public_disabled(query: CallbackQuery) -> None:
    await query.answer("Публичные комнаты пока недоступны.", show_alert=True)

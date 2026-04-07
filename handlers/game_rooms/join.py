from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.controllers.room import (
    InvalidRoomPasswordError,
    RoomControllerError,
    RoomIsFullError,
    RoomLookupResult,
    RoomNotFoundError,
    UserAlreadyInRoomError,
    get_room_lookup_by_code,
    get_user_room_snapshot,
    join_room_for_user,
)
from database.controllers.ui_state import set_menu_message_id
from handlers.common import edit_menu_caption
from handlers.game_rooms.helpers import clear_state_keep_menu_message, get_menu_message_id, safe_delete_message
from handlers.game_rooms.keyboards import join_input_keyboard, join_menu_keyboard
from handlers.game_rooms.states import RoomState
from handlers.game_rooms.views import broadcast_room_update, render_room_lobby

router = Router()


@router.callback_query(F.data == "game_join")
async def callback_game_join(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await set_menu_message_id(query.from_user.id, query.message.message_id)

    snapshot = await get_user_room_snapshot(query.from_user.id)
    if snapshot is not None:
        await clear_state_keep_menu_message(state)
        await state.update_data(menu_message_id=query.message.message_id)
        await render_room_lobby(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            viewer_tg_user_id=query.from_user.id,
            snapshot=snapshot,
            prefix="Ты уже состоишь в комнате.",
        )
        return

    await clear_state_keep_menu_message(state)
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Присоединение к игре\n\nВыбери вариант входа в комнату.",
        keyboard=join_menu_keyboard(),
    )


@router.callback_query(F.data == "game_join_by_code")
async def callback_game_join_by_code(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(RoomState.waiting_join_code)
    await state.update_data(menu_message_id=query.message.message_id)
    await set_menu_message_id(query.from_user.id, query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Присоединение по коду\n\nОтправь код комнаты одним сообщением.",
        keyboard=join_input_keyboard(),
    )


@router.message(RoomState.waiting_join_code)
async def handle_join_room_code(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    menu_message_id = await get_menu_message_id(state)
    if not menu_message_id:
        await state.clear()
        return

    room_code = (message.text or "").strip().upper()
    if len(room_code) < 4:
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Код комнаты слишком короткий. Отправь корректный код.",
            keyboard=join_input_keyboard(),
        )
        return

    room_lookup: Optional[RoomLookupResult] = await get_room_lookup_by_code(room_code)
    if room_lookup is None:
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Код комнаты неверный. Проверь код и отправь его снова.",
            keyboard=join_input_keyboard(),
        )
        return

    await state.update_data(join_room_code=room_code)
    await state.update_data(join_room_title=room_lookup.title)
    await state.set_state(RoomState.waiting_join_password)
    await edit_menu_caption(
        chat_id=message.chat.id,
        message_id=menu_message_id,
        text='Присоединение по коду\n\nВведи пароль для комнаты "{}".'.format(room_lookup.title),
        keyboard=join_input_keyboard(),
    )


@router.message(RoomState.waiting_join_password)
async def handle_join_room_password(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    menu_message_id = await get_menu_message_id(state)
    if not menu_message_id:
        await state.clear()
        return

    data = await state.get_data()
    room_code = data.get("join_room_code")
    room_title = data.get("join_room_title")
    password = (message.text or "").strip()

    if not room_code:
        await state.set_state(RoomState.waiting_join_code)
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Сначала отправь код комнаты.",
            keyboard=join_input_keyboard(),
        )
        return

    try:
        snapshot = await join_room_for_user(message.from_user.id, room_code, password)
    except UserAlreadyInRoomError as exc:
        await clear_state_keep_menu_message(state)
        await state.update_data(menu_message_id=menu_message_id)
        await render_room_lobby(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            viewer_tg_user_id=message.from_user.id,
            snapshot=exc.room_snapshot,
            prefix="Ты уже состоишь в другой комнате.",
        )
        return
    except RoomNotFoundError:
        await state.set_state(RoomState.waiting_join_code)
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Комната не найдена или уже аннулирована. Отправь код комнаты заново.",
            keyboard=join_input_keyboard(),
        )
        return
    except InvalidRoomPasswordError:
        await state.set_state(RoomState.waiting_join_password)
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text='Неверный пароль. Попробуй снова для комнаты "{}".'.format(room_title or room_code),
            keyboard=join_input_keyboard(),
        )
        return
    except RoomIsFullError:
        await state.set_state(RoomState.waiting_join_code)
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Комната заполнена. Отправь другой код комнаты.",
            keyboard=join_input_keyboard(),
        )
        return
    except RoomControllerError as exc:
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Не удалось присоединиться к комнате: {}".format(str(exc)),
            keyboard=join_input_keyboard(),
        )
        return

    await clear_state_keep_menu_message(state)
    await state.update_data(menu_message_id=menu_message_id)
    await render_room_lobby(
        chat_id=message.chat.id,
        message_id=menu_message_id,
        viewer_tg_user_id=message.from_user.id,
        snapshot=snapshot,
        prefix="Вы присоединились к комнате.",
    )
    await set_menu_message_id(message.from_user.id, menu_message_id)
    await broadcast_room_update(
        snapshot,
        prefix_by_user_id={message.from_user.id: "Вы присоединились к комнате."},
    )

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.controllers.room import (
    MAX_ROOM_PLAYERS,
    MIN_ROOM_PLAYERS,
    InvalidRoomConfigError,
    RoomControllerError,
    UserAlreadyInRoomError,
    create_room_for_user,
    get_user_room_snapshot,
)
from database.controllers.ui_state import set_menu_message_id
from handlers.common import edit_menu_caption
from handlers.game_rooms.helpers import clear_state_keep_menu_message, get_menu_message_id, safe_delete_message
from handlers.game_rooms.keyboards import (
    create_settings_keyboard,
    join_input_keyboard,
)
from handlers.game_rooms.states import DEFAULT_ROOM_PLAYERS, RoomState
from handlers.game_rooms.views import render_create_draft, render_room_lobby, verify_pending_group_link

router = Router()


@router.callback_query(F.data == "game_create")
async def callback_game_create(query: CallbackQuery, state: FSMContext) -> None:
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
    await state.update_data(create_draft_max_players=DEFAULT_ROOM_PLAYERS)
    await state.set_state(RoomState.waiting_create_room_name)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Создание комнаты\n\nОтправь название комнаты (2-64 символа).",
        keyboard=join_input_keyboard(),
    )


@router.message(RoomState.waiting_create_room_name)
async def handle_create_room_name(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    menu_message_id = await get_menu_message_id(state)
    if not menu_message_id:
        await state.clear()
        return

    room_name = (message.text or "").strip()
    if len(room_name) < 2 or len(room_name) > 64:
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Создание комнаты\n\nНазвание должно быть от 2 до 64 символов. Отправь снова.",
            keyboard=join_input_keyboard(),
        )
        return

    await state.update_data(create_draft_title=room_name)
    await state.set_state(RoomState.waiting_create_chat_link)
    await edit_menu_caption(
        chat_id=message.chat.id,
        message_id=menu_message_id,
        text=(
            "Создание комнаты\n\n"
            "Шаг 2 из 4.\n"
            "Создай групповой чат, добавь туда бота и выдай права администратора.\n"
            "После этого отправь публичную ссылку на этот чат одним сообщением.\n"
            "Формат: t.me/group_name"
        ),
        keyboard=join_input_keyboard(),
    )


@router.message(RoomState.waiting_create_chat_link)
async def handle_create_chat_link(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    menu_message_id = await get_menu_message_id(state)
    if not menu_message_id:
        await state.clear()
        return

    chat_link = (message.text or "").strip()
    await verify_pending_group_link(
        chat_id=message.chat.id,
        message_id=menu_message_id,
        state=state,
        chat_link=chat_link,
    )


@router.callback_query(F.data == "create_chat_link_recheck")
async def callback_create_chat_link_recheck(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    data = await state.get_data()
    chat_link = data.get("create_draft_chat_link_candidate")
    if not chat_link:
        await edit_menu_caption(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            text=(
                "Ссылка для повторной проверки не найдена.\n\n"
                "Отправь ссылку на группу еще раз."
            ),
            keyboard=join_input_keyboard(),
        )
        return

    await verify_pending_group_link(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        state=state,
        chat_link=chat_link,
    )


@router.callback_query(F.data == "create_chat_link_change")
async def callback_create_chat_link_change(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(RoomState.waiting_create_chat_link)
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=(
            "Создание комнаты\n\n"
            "Отправь другую публичную ссылку на группу.\n"
            "Формат: t.me/group_name"
        ),
        keyboard=join_input_keyboard(),
    )


@router.callback_query(F.data == "create_visibility_private")
async def callback_create_visibility_private(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(RoomState.waiting_create_password)
    await state.update_data(menu_message_id=query.message.message_id)
    await set_menu_message_id(query.from_user.id, query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=(
            "Создание комнаты\n\n"
            "Шаг 4 из 4.\n"
            "Придумай пароль для приватной комнаты (4-32 символа) и отправь его."
        ),
        keyboard=join_input_keyboard(),
    )


@router.message(RoomState.waiting_create_password)
async def handle_create_room_password(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    menu_message_id = await get_menu_message_id(state)
    if not menu_message_id:
        await state.clear()
        return

    password = (message.text or "").strip()
    if len(password) < 4 or len(password) > 32:
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Пароль должен быть от 4 до 32 символов. Отправь пароль заново.",
            keyboard=join_input_keyboard(),
        )
        return

    await state.update_data(create_draft_password=password)
    await state.set_state(None)
    await render_create_draft(
        chat_id=message.chat.id,
        message_id=menu_message_id,
        state=state,
    )


@router.callback_query(F.data == "create_players_dec")
async def callback_create_players_dec(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    data = await state.get_data()
    current_value = int(data.get("create_draft_max_players", DEFAULT_ROOM_PLAYERS))
    current_value = max(MIN_ROOM_PLAYERS, current_value - 1)
    await state.update_data(create_draft_max_players=current_value, menu_message_id=query.message.message_id)
    await render_create_draft(query.message.chat.id, query.message.message_id, state)


@router.callback_query(F.data == "create_players_inc")
async def callback_create_players_inc(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    data = await state.get_data()
    current_value = int(data.get("create_draft_max_players", DEFAULT_ROOM_PLAYERS))
    current_value = min(MAX_ROOM_PLAYERS, current_value + 1)
    await state.update_data(create_draft_max_players=current_value, menu_message_id=query.message.message_id)
    await render_create_draft(query.message.chat.id, query.message.message_id, state)


@router.callback_query(F.data == "create_settings_open")
async def callback_create_settings_open(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(None)
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Настройки конструктора\n\nВыбери, что хочешь изменить.",
        keyboard=create_settings_keyboard(),
    )


@router.callback_query(F.data == "create_settings_back")
async def callback_create_settings_back(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(None)
    await state.update_data(menu_message_id=query.message.message_id)
    await render_create_draft(query.message.chat.id, query.message.message_id, state)


@router.callback_query(F.data == "create_settings_change_name")
async def callback_create_settings_change_name(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(RoomState.waiting_create_settings_name)
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Отправь новое название комнаты (2-64 символа).",
        keyboard=create_settings_keyboard(),
    )


@router.callback_query(F.data == "create_settings_change_password")
async def callback_create_settings_change_password(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(RoomState.waiting_create_settings_password)
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Отправь новый пароль комнаты (4-32 символа).",
        keyboard=create_settings_keyboard(),
    )


@router.message(RoomState.waiting_create_settings_name)
async def handle_create_settings_name(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    menu_message_id = await get_menu_message_id(state)
    if not menu_message_id:
        await state.clear()
        return

    new_name = (message.text or "").strip()
    if len(new_name) < 2 or len(new_name) > 64:
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Название должно быть от 2 до 64 символов. Отправь снова.",
            keyboard=create_settings_keyboard(),
        )
        return

    await state.update_data(create_draft_title=new_name)
    await state.set_state(None)
    await render_create_draft(message.chat.id, menu_message_id, state)


@router.message(RoomState.waiting_create_settings_password)
async def handle_create_settings_password(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    menu_message_id = await get_menu_message_id(state)
    if not menu_message_id:
        await state.clear()
        return

    new_password = (message.text or "").strip()
    if len(new_password) < 4 or len(new_password) > 32:
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text="Пароль должен быть от 4 до 32 символов. Отправь снова.",
            keyboard=create_settings_keyboard(),
        )
        return

    await state.update_data(create_draft_password=new_password)
    await state.set_state(None)
    await render_create_draft(message.chat.id, menu_message_id, state)


@router.callback_query(F.data == "create_finalize")
async def callback_create_finalize(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await set_menu_message_id(query.from_user.id, query.message.message_id)
    data = await state.get_data()
    room_title = data.get("create_draft_title")
    room_password = data.get("create_draft_password")
    room_link = data.get("create_draft_chat_link")
    room_group_chat_id = data.get("create_draft_group_chat_id")
    room_max_players = int(data.get("create_draft_max_players", DEFAULT_ROOM_PLAYERS))

    if not room_title or not room_password or not room_link:
        await render_create_draft(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            state=state,
            prefix="Не все поля заполнены. Проверь настройки комнаты.",
        )
        return

    try:
        snapshot = await create_room_for_user(
            tg_user_id=query.from_user.id,
            title=room_title,
            max_players=room_max_players,
            password=room_password,
            group_link=room_link,
            group_chat_id=int(room_group_chat_id) if room_group_chat_id is not None else None,
        )
    except UserAlreadyInRoomError as exc:
        await clear_state_keep_menu_message(state)
        await state.update_data(menu_message_id=query.message.message_id)
        await render_room_lobby(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            viewer_tg_user_id=query.from_user.id,
            snapshot=exc.room_snapshot,
            prefix="Ты уже в активной комнате.",
        )
        return
    except InvalidRoomConfigError as exc:
        await render_create_draft(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            state=state,
            prefix=str(exc),
        )
        return
    except RoomControllerError as exc:
        await render_create_draft(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            state=state,
            prefix="Не удалось создать комнату: {}".format(str(exc)),
        )
        return

    await clear_state_keep_menu_message(state)
    await state.update_data(menu_message_id=query.message.message_id)
    await render_room_lobby(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        viewer_tg_user_id=query.from_user.id,
        snapshot=snapshot,
        prefix="Комната создана.",
    )
    from handlers.game_rooms.views import broadcast_room_update
    await broadcast_room_update(snapshot)

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from core.telegram import bot
from database.controllers.room import (
    KickPlayerResult,
    LeaveRoomResult,
    RoomControllerError,
    get_user_room_snapshot,
    kick_player_from_room,
    leave_room_for_user,
    set_room_max_players_for_owner,
    toggle_ready_for_user,
    update_room_game_mode_for_owner,
    update_room_max_players_for_owner,
    update_room_name_for_owner,
    update_room_password_for_owner,
)
from database.controllers.room_roles import get_custom_role_config_for_owner
from database.controllers.room_roles import update_custom_role_count_for_owner
from database.controllers.ui_state import get_room_message_targets, set_menu_message_id
from handlers.common import edit_menu_caption
from handlers.game_rooms.helpers import (
    clear_state_keep_menu_message,
    get_menu_message_id,
    is_owner,
    safe_delete_message,
)
from handlers.game_rooms.keyboards import (
    owner_kick_players_keyboard,
    owner_room_reduce_prompt_keyboard,
    owner_room_settings_keyboard,
)
from handlers.game_rooms.states import RoomState
from handlers.game_rooms.views import broadcast_room_update, render_game_menu, render_room_lobby
from handlers.game_rooms.views import render_owner_custom_role_settings
from handlers.game_rooms.views import render_owner_game_settings
from utils.group_verifier import verify_user_in_group

router = Router()


@router.callback_query(F.data == "room_leave")
async def callback_room_leave(query: CallbackQuery, state: FSMContext) -> None:
    snapshot_before_leave = await get_user_room_snapshot(query.from_user.id)
    targets_before_leave = []
    if snapshot_before_leave is not None:
        targets_before_leave = await get_room_message_targets(snapshot_before_leave.room_id)

    await query.answer()
    result: LeaveRoomResult = await leave_room_for_user(query.from_user.id)
    await clear_state_keep_menu_message(state)
    await state.update_data(menu_message_id=query.message.message_id)
    await set_menu_message_id(query.from_user.id, query.message.message_id)

    if not result.had_room:
        await render_game_menu(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            prefix="Ты не состоишь в активной комнате.",
        )
        return

    if result.owner_deleted_room:
        targets_map = {tg_user_id: message_id for tg_user_id, message_id in targets_before_leave}
        for player in snapshot_before_leave.players if snapshot_before_leave else []:
            if player.tg_user_id == query.from_user.id:
                continue
            message_id = targets_map.get(player.tg_user_id)
            if not message_id:
                continue
            try:
                await render_game_menu(
                    chat_id=player.tg_user_id,
                    message_id=message_id,
                    prefix="Владелец закрыл комнату. Ты исключен из нее.",
                )
            except TelegramBadRequest:
                continue
        await render_game_menu(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            prefix="Ты вышел как владелец. Комната удалена, участники исключены.",
        )
        return

    snapshot_after_leave = None
    if snapshot_before_leave is not None:
        for player in snapshot_before_leave.players:
            if player.tg_user_id != query.from_user.id:
                snapshot_after_leave = await get_user_room_snapshot(player.tg_user_id)
                if snapshot_after_leave is not None:
                    break

    if snapshot_after_leave is not None:
        await broadcast_room_update(snapshot_after_leave)

    await render_game_menu(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        prefix="Ты вышел из комнаты.",
    )


@router.callback_query(F.data == "room_toggle_ready")
async def callback_room_toggle_ready(query: CallbackQuery, state: FSMContext) -> None:
    current_snapshot = await get_user_room_snapshot(query.from_user.id)
    if current_snapshot is None:
        await query.answer("Комната недоступна.", show_alert=True)
        await clear_state_keep_menu_message(state)
        await state.update_data(menu_message_id=query.message.message_id)
        await set_menu_message_id(query.from_user.id, query.message.message_id)
        await render_game_menu(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            prefix="Комната недоступна.",
        )
        return

    membership = await verify_user_in_group(bot, current_snapshot.group_link or "", query.from_user.id)
    if not membership.ok:
        await query.answer(membership.message, show_alert=True)
        return

    try:
        snapshot = await toggle_ready_for_user(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        snapshot = await get_user_room_snapshot(query.from_user.id)
        if snapshot is None:
            await clear_state_keep_menu_message(state)
            await state.update_data(menu_message_id=query.message.message_id)
            await render_game_menu(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                prefix="Комната недоступна.",
            )
            return

    await query.answer()
    await state.update_data(menu_message_id=query.message.message_id)
    await set_menu_message_id(query.from_user.id, query.message.message_id)
    await broadcast_room_update(snapshot)


@router.callback_query(F.data == "room_owner_dec_players")
async def callback_room_owner_dec_players(query: CallbackQuery, state: FSMContext) -> None:
    snapshot_before = await get_user_room_snapshot(query.from_user.id)
    if snapshot_before is None or not is_owner(snapshot_before, query.from_user.id):
        await query.answer("Комната недоступна.", show_alert=True)
        return

    from database.controllers.room import MIN_ROOM_PLAYERS

    target_value = max(MIN_ROOM_PLAYERS, snapshot_before.max_players - 1)
    if target_value < snapshot_before.players_count:
        await query.answer()
        await state.update_data(menu_message_id=query.message.message_id)
        await state.update_data(owner_pending_target_players=target_value)
        await edit_menu_caption(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            text=(
                "Ты можешь уменьшить количество игроков только если кикнешь кого-то.\n\n"
                "Хочешь выбрать игрока для кика?"
            ),
            keyboard=owner_room_reduce_prompt_keyboard(),
        )
        return

    try:
        snapshot = await update_room_max_players_for_owner(query.from_user.id, delta=-1)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer()
    await state.update_data(menu_message_id=query.message.message_id)
    await broadcast_room_update(snapshot)


@router.callback_query(F.data == "room_owner_inc_players")
async def callback_room_owner_inc_players(query: CallbackQuery, state: FSMContext) -> None:
    try:
        snapshot = await update_room_max_players_for_owner(query.from_user.id, delta=1)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer()
    await state.update_data(menu_message_id=query.message.message_id)
    await broadcast_room_update(snapshot)


@router.callback_query(F.data == "room_owner_kick_open")
async def callback_room_owner_kick_open(query: CallbackQuery, state: FSMContext) -> None:
    snapshot = await get_user_room_snapshot(query.from_user.id)
    if snapshot is None or not is_owner(snapshot, query.from_user.id):
        await query.answer("Только владелец может кикать игроков.", show_alert=True)
        return

    kickable_players = [player for player in snapshot.players if not player.is_owner]
    if not kickable_players:
        await query.answer("В комнате нет игроков для кика.", show_alert=True)
        return

    await query.answer()
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Выберите игрока которого хотите выгнать.",
        keyboard=owner_kick_players_keyboard(snapshot),
    )


@router.callback_query(F.data == "room_owner_kick_cancel")
async def callback_room_owner_kick_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.update_data(menu_message_id=query.message.message_id)
    await state.update_data(owner_pending_target_players=None)
    snapshot = await get_user_room_snapshot(query.from_user.id)
    if snapshot is None:
        await render_game_menu(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            prefix="Комната недоступна.",
        )
        return

    await render_room_lobby(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        viewer_tg_user_id=query.from_user.id,
        snapshot=snapshot,
    )


@router.callback_query(F.data.startswith("room_owner_kick_select_"))
async def callback_room_owner_kick_select(query: CallbackQuery, state: FSMContext) -> None:
    try:
        target_tg_user_id = int(query.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Не удалось определить игрока.", show_alert=True)
        return

    snapshot_before = await get_user_room_snapshot(query.from_user.id)
    targets_before = []
    if snapshot_before is not None:
        targets_before = await get_room_message_targets(snapshot_before.room_id)

    try:
        kick_result: KickPlayerResult = await kick_player_from_room(query.from_user.id, target_tg_user_id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    data = await state.get_data()
    pending_target = data.get("owner_pending_target_players")
    snapshot = kick_result.snapshot
    owner_prefix = 'Игрок "{}" исключен из комнаты.'.format(kick_result.kicked_player_name)

    if pending_target is not None and snapshot.players_count <= int(pending_target):
        try:
            snapshot = await set_room_max_players_for_owner(query.from_user.id, int(pending_target))
            owner_prefix = (
                'Игрок "{}" исключен из комнаты. Лимит игроков уменьшен до {}.'
            ).format(kick_result.kicked_player_name, int(pending_target))
        except RoomControllerError:
            pass

    await query.answer()
    await state.update_data(menu_message_id=query.message.message_id)
    await state.update_data(owner_pending_target_players=None)
    targets_map = {tg_user_id: message_id for tg_user_id, message_id in targets_before}
    kicked_message_id = targets_map.get(kick_result.kicked_player_tg_user_id)
    if kicked_message_id:
        try:
            await render_game_menu(
                chat_id=kick_result.kicked_player_tg_user_id,
                message_id=kicked_message_id,
                prefix='Тебя исключили из комнаты "{}".'.format(snapshot.title),
            )
        except TelegramBadRequest:
            pass
    await render_room_lobby(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        viewer_tg_user_id=query.from_user.id,
        snapshot=snapshot,
        prefix=owner_prefix,
    )
    await broadcast_room_update(
        snapshot,
        prefix_by_user_id={query.from_user.id: owner_prefix},
    )


@router.callback_query(F.data == "room_owner_settings_open")
async def callback_room_owner_settings_open(query: CallbackQuery, state: FSMContext) -> None:
    snapshot = await get_user_room_snapshot(query.from_user.id)
    if snapshot is None or not is_owner(snapshot, query.from_user.id):
        await query.answer("Только владелец может менять настройки комнаты.", show_alert=True)
        return

    await query.answer()
    await state.set_state(None)
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=(
            "Настройки комнаты\n\n"
            "Комната: {}\n"
            "Код: {}\n"
            "Выбери параметр для изменения."
        ).format(snapshot.title, snapshot.code),
        keyboard=owner_room_settings_keyboard(),
    )


@router.callback_query(F.data == "room_owner_game_settings_open")
async def callback_room_owner_game_settings_open(query: CallbackQuery, state: FSMContext) -> None:
    snapshot = await get_user_room_snapshot(query.from_user.id)
    if snapshot is None or not is_owner(snapshot, query.from_user.id):
        await query.answer("Только владелец может менять формат игры.", show_alert=True)
        return

    await query.answer()
    await state.set_state(None)
    await state.update_data(menu_message_id=query.message.message_id)
    await render_owner_game_settings(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        snapshot=snapshot,
    )


@router.callback_query(F.data == "room_owner_game_settings_back")
async def callback_room_owner_game_settings_back(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    snapshot = await get_user_room_snapshot(query.from_user.id)
    if snapshot is None:
        await render_game_menu(query.message.chat.id, query.message.message_id, prefix="Комната недоступна.")
        return

    await state.set_state(None)
    await state.update_data(menu_message_id=query.message.message_id)
    await render_room_lobby(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        viewer_tg_user_id=query.from_user.id,
        snapshot=snapshot,
    )


@router.callback_query(F.data == "room_owner_game_mode_classic")
async def callback_room_owner_game_mode_classic(query: CallbackQuery, state: FSMContext) -> None:
    await _update_room_game_mode(
        query=query,
        state=state,
        game_mode="classic",
        success_prefix="Формат игры переключен на классику.",
    )


@router.callback_query(F.data == "room_owner_game_mode_custom")
async def callback_room_owner_game_mode_custom(query: CallbackQuery, state: FSMContext) -> None:
    await _update_room_game_mode(
        query=query,
        state=state,
        game_mode="custom",
        success_prefix="Формат игры переключен на кастом.",
    )


async def _update_room_game_mode(query: CallbackQuery, state: FSMContext, game_mode: str, success_prefix: str) -> None:
    try:
        snapshot = await update_room_game_mode_for_owner(query.from_user.id, game_mode)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer()
    await state.update_data(menu_message_id=query.message.message_id)
    await render_owner_game_settings(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        snapshot=snapshot,
        prefix=success_prefix,
    )
    await broadcast_room_update(snapshot, skip_user_ids={query.from_user.id})


@router.callback_query(F.data == "room_owner_game_roles_blocked")
async def callback_room_owner_game_roles_blocked(query: CallbackQuery) -> None:
    await query.answer(
        "В классическом режиме роли фиксированы. Для ручной настройки переключись на режим Кастом.",
        show_alert=True,
    )


@router.callback_query(F.data == "room_owner_game_roles_open")
async def callback_room_owner_game_roles_open(query: CallbackQuery, state: FSMContext) -> None:
    try:
        role_config_snapshot = await get_custom_role_config_for_owner(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer()
    await state.update_data(menu_message_id=query.message.message_id)
    await render_owner_custom_role_settings(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        snapshot=role_config_snapshot,
        owner_tg_user_id=query.from_user.id,
    )


@router.callback_query(F.data.startswith("room_owner_role_dec_"))
async def callback_room_owner_role_dec(query: CallbackQuery, state: FSMContext) -> None:
    await _update_custom_role_count(query, state, delta=-1)


@router.callback_query(F.data.startswith("room_owner_role_inc_"))
async def callback_room_owner_role_inc(query: CallbackQuery, state: FSMContext) -> None:
    await _update_custom_role_count(query, state, delta=1)


async def _update_custom_role_count(query: CallbackQuery, state: FSMContext, delta: int) -> None:
    try:
        role_key = query.data.rsplit("_", 1)[1]
    except (AttributeError, IndexError):
        await query.answer("Не удалось определить роль.", show_alert=True)
        return

    try:
        role_config_snapshot = await update_custom_role_count_for_owner(
            owner_tg_user_id=query.from_user.id,
            role_key=role_key,
            delta=delta,
        )
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer()
    await state.update_data(menu_message_id=query.message.message_id)
    await render_owner_custom_role_settings(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        snapshot=role_config_snapshot,
        owner_tg_user_id=query.from_user.id,
    )


@router.callback_query(F.data == "room_owner_settings_back")
async def callback_room_owner_settings_back(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    snapshot = await get_user_room_snapshot(query.from_user.id)
    if snapshot is None:
        await render_game_menu(query.message.chat.id, query.message.message_id, prefix="Комната недоступна.")
        return

    await state.set_state(None)
    await state.update_data(menu_message_id=query.message.message_id)
    await render_room_lobby(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        viewer_tg_user_id=query.from_user.id,
        snapshot=snapshot,
    )


@router.callback_query(F.data == "room_owner_settings_change_name")
async def callback_room_owner_settings_change_name(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(RoomState.waiting_owner_room_name)
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Отправь новое название комнаты (2-64 символа).",
        keyboard=owner_room_settings_keyboard(),
    )


@router.callback_query(F.data == "room_owner_settings_change_password")
async def callback_room_owner_settings_change_password(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(RoomState.waiting_owner_room_password)
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Отправь новый пароль комнаты (4-32 символа).",
        keyboard=owner_room_settings_keyboard(),
    )


@router.message(RoomState.waiting_owner_room_name)
async def handle_owner_room_name(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    menu_message_id = await get_menu_message_id(state)
    if not menu_message_id:
        await state.clear()
        return

    new_name = (message.text or "").strip()
    try:
        snapshot = await update_room_name_for_owner(message.from_user.id, new_name)
    except RoomControllerError as exc:
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text=str(exc),
            keyboard=owner_room_settings_keyboard(),
        )
        return

    await clear_state_keep_menu_message(state)
    await state.update_data(menu_message_id=menu_message_id)
    await broadcast_room_update(
        snapshot,
        prefix_by_user_id={message.from_user.id: "Название комнаты обновлено."},
    )


@router.message(RoomState.waiting_owner_room_password)
async def handle_owner_room_password(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    menu_message_id = await get_menu_message_id(state)
    if not menu_message_id:
        await state.clear()
        return

    new_password = (message.text or "").strip()
    try:
        snapshot = await update_room_password_for_owner(message.from_user.id, new_password)
    except RoomControllerError as exc:
        await edit_menu_caption(
            chat_id=message.chat.id,
            message_id=menu_message_id,
            text=str(exc),
            keyboard=owner_room_settings_keyboard(),
        )
        return

    await clear_state_keep_menu_message(state)
    await state.update_data(menu_message_id=menu_message_id)
    await broadcast_room_update(
        snapshot,
        prefix_by_user_id={message.from_user.id: "Пароль комнаты обновлен."},
    )


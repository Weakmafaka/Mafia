from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from core.telegram import bot
from database.controllers.game_flow import (
    ROLE_STAGE_META,
    RoomControllerError,
    get_stage_snapshot_for_user,
    set_generic_stage_skip,
    set_generic_stage_target,
    toggle_generic_stage_ready,
)
from handlers.game_rooms.stage_keyboards import stage_target_keyboard
from handlers.game_rooms.stage_runtime import launch_stage_advance
from handlers.game_rooms.stage_views import broadcast_stage_update
from handlers.game_rooms.stage_views import build_stage_group_text
from handlers.game_rooms.stage_views import render_stage_group_message

router = Router()


@router.callback_query(F.data == "stage_open_targets")
async def callback_stage_open_targets(query: CallbackQuery) -> None:
    try:
        snapshot = await get_stage_snapshot_for_user(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer()
    await bot.edit_message_text(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="{}\n\nВыбери цель.".format(build_stage_group_text(snapshot)),
        reply_markup=stage_target_keyboard(snapshot, query.from_user.id),
    )


@router.callback_query(F.data == "stage_back_to_main")
async def callback_stage_back_to_main(query: CallbackQuery) -> None:
    try:
        snapshot = await get_stage_snapshot_for_user(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await query.answer()
    await render_stage_group_message(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        snapshot=snapshot,
    )


@router.callback_query(F.data.startswith("stage_target_"))
async def callback_stage_target(query: CallbackQuery) -> None:
    try:
        target_tg_user_id = int(query.data.rsplit("_", 1)[1])
    except (TypeError, ValueError, IndexError):
        await query.answer("Не удалось определить цель.", show_alert=True)
        return

    try:
        snapshot = await set_generic_stage_target(query.from_user.id, target_tg_user_id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await query.answer("Выбор сохранен.")
    await broadcast_stage_update(snapshot)


@router.callback_query(F.data == "stage_select_skip")
async def callback_stage_select_skip(query: CallbackQuery) -> None:
    try:
        snapshot = await set_generic_stage_skip(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await query.answer(ROLE_STAGE_META[snapshot.stage]["skip_text"])
    await broadcast_stage_update(snapshot)


@router.callback_query(F.data == "stage_ready_blocked")
async def callback_stage_ready_blocked(query: CallbackQuery) -> None:
    await query.answer("Сначала выбери цель или пропуск.", show_alert=True)


@router.callback_query(F.data == "stage_ready_toggle")
async def callback_stage_ready_toggle(query: CallbackQuery) -> None:
    try:
        snapshot, advance_result, became_ready = await toggle_generic_stage_ready(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    if advance_result is not None:
        await query.answer("Ход зафиксирован.")
        await launch_stage_advance(advance_result)
        return

    await query.answer("Готовность включена." if became_ready else "Готовность снята.")
    await broadcast_stage_update(snapshot)

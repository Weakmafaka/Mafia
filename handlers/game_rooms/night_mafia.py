import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from core.telegram import bot
from database.controllers.mafia_turn import (
    MafiaTurnFinalizeResult,
    MafiaTurnSnapshot,
    RoomControllerError,
    finalize_mafia_turn_on_timeout,
    get_mafia_turn_snapshot_for_room,
    get_mafia_turn_snapshot_for_user,
    set_mafia_skip_choice,
    set_mafia_vote_target,
    toggle_mafia_ready,
)
from database.controllers.game_flow import advance_after_mafia_resolution
from database.controllers.game_flow import set_stage_group_message_id
from game.classic_mafia.narrator import build_first_night_message
from game.classic_mafia.narrator import build_mafia_resolution_message
from handlers.game_rooms.night_keyboards import mafia_vote_targets_keyboard
from handlers.game_rooms.stage_runtime import launch_stage_advance
from handlers.game_rooms.night_views import broadcast_mafia_turn_update
from handlers.game_rooms.night_views import build_mafia_turn_text
from handlers.game_rooms.night_views import render_mafia_turn_message
from utils.group_verifier import resolve_group_chat

router = Router()

_MAFIA_TIMEOUT_TASKS: Dict[int, asyncio.Task] = {}


async def _resolve_group_chat_id(snapshot: MafiaTurnSnapshot) -> Optional[int]:
    if snapshot.group_chat_id is not None:
        return int(snapshot.group_chat_id)
    if not snapshot.group_link:
        return None

    resolved = await resolve_group_chat(bot, snapshot.group_link)
    if not resolved.ok:
        return None
    return resolved.chat_id


async def _send_group_announcement(snapshot: MafiaTurnSnapshot, text: str) -> None:
    chat_id = await _resolve_group_chat_id(snapshot)
    if chat_id is None:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except TelegramBadRequest:
        return


async def _announce_mafia_resolution(finalize_result: MafiaTurnFinalizeResult) -> None:
    await _send_group_announcement(
        finalize_result.snapshot,
        build_mafia_resolution_message(finalize_result.source),
    )


def _schedule_timeout(snapshot: MafiaTurnSnapshot) -> None:
    existing_task = _MAFIA_TIMEOUT_TASKS.pop(snapshot.game_session_id, None)
    if existing_task is not None:
        existing_task.cancel()

    async def _runner() -> None:
        try:
            if snapshot.deadline_at is None:
                return
            await asyncio.sleep(
                max(0, (snapshot.deadline_at - datetime.now(timezone.utc)).total_seconds())
            )
            finalize_result = await finalize_mafia_turn_on_timeout(snapshot.game_session_id)
            if finalize_result is None:
                return
            await _announce_mafia_resolution(finalize_result)
            await broadcast_mafia_turn_update(
                finalize_result.snapshot,
                prefix_by_user_id={
                    member.tg_user_id: (
                        "Время вышло, бот зафиксировал лидирующий выбор."
                        if finalize_result.source == "timeout_existing_votes"
                        else "Время вышло, бот выбрал ход случайно."
                    )
                    for member in finalize_result.snapshot.members
                },
            )
            advance_result = await advance_after_mafia_resolution(finalize_result.snapshot.room_id)
            await launch_stage_advance(advance_result)
        finally:
            _MAFIA_TIMEOUT_TASKS.pop(snapshot.game_session_id, None)

    _MAFIA_TIMEOUT_TASKS[snapshot.game_session_id] = asyncio.create_task(_runner())


async def start_mafia_turn_flow(room_id: int, group_message: Optional[str] = None) -> None:
    snapshot = await get_mafia_turn_snapshot_for_room(room_id)
    if not snapshot.members:
        return

    chat_id = await _resolve_group_chat_id(snapshot)
    if chat_id is None:
        return
    try:
        sent_message = await bot.send_message(
            chat_id=chat_id,
            text=build_mafia_turn_text(
                snapshot,
                0,
                prefix=group_message or build_first_night_message("mafia", snapshot.night_number),
            ),
            reply_markup=None,
        )
    except TelegramBadRequest:
        return
    await set_stage_group_message_id(snapshot.game_session_id, sent_message.message_id)

    refreshed_snapshot = await get_mafia_turn_snapshot_for_room(room_id)
    refreshed_snapshot.group_message_id = sent_message.message_id
    await broadcast_mafia_turn_update(refreshed_snapshot)
    _schedule_timeout(refreshed_snapshot)


@router.callback_query(F.data == "mafia_turn_noop")
async def callback_mafia_turn_noop(query: CallbackQuery) -> None:
    await query.answer()


@router.callback_query(F.data == "mafia_open_vote_targets")
async def callback_mafia_open_vote_targets(query: CallbackQuery) -> None:
    try:
        snapshot = await get_mafia_turn_snapshot_for_user(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    if snapshot.is_resolved:
        await query.answer("Ход мафии уже зафиксирован.", show_alert=True)
        return

    await query.answer()
    await bot.edit_message_text(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=(
            "{}\n\n"
            "Выбери игрока, за которого хочешь проголосовать."
        ).format(build_mafia_turn_text(snapshot, query.from_user.id)),
        reply_markup=mafia_vote_targets_keyboard(snapshot),
    )


@router.callback_query(F.data == "mafia_back_to_main")
async def callback_mafia_back_to_main(query: CallbackQuery) -> None:
    try:
        snapshot = await get_mafia_turn_snapshot_for_user(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer()
    await render_mafia_turn_message(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        snapshot=snapshot,
        viewer_tg_user_id=query.from_user.id,
    )


@router.callback_query(F.data.startswith("mafia_vote_target_"))
async def callback_mafia_vote_target(query: CallbackQuery) -> None:
    try:
        target_tg_user_id = int(query.data.rsplit("_", 1)[1])
    except (TypeError, ValueError, IndexError):
        await query.answer("Не удалось определить цель.", show_alert=True)
        return

    try:
        snapshot = await set_mafia_vote_target(query.from_user.id, target_tg_user_id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer("Выбор сохранен.")
    await broadcast_mafia_turn_update(snapshot)


@router.callback_query(F.data == "mafia_select_skip")
async def callback_mafia_select_skip(query: CallbackQuery) -> None:
    try:
        snapshot = await set_mafia_skip_choice(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer("Пропуск выбран.")
    await broadcast_mafia_turn_update(snapshot)


@router.callback_query(F.data == "mafia_ready_blocked")
async def callback_mafia_ready_blocked(query: CallbackQuery) -> None:
    await query.answer("Сначала выбери жертву или пропуск.", show_alert=True)


@router.callback_query(F.data == "mafia_ready_toggle")
async def callback_mafia_ready_toggle(query: CallbackQuery) -> None:
    try:
        snapshot, finalize_result, became_ready = await toggle_mafia_ready(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    if finalize_result is not None:
        scheduled_task = _MAFIA_TIMEOUT_TASKS.pop(finalize_result.snapshot.game_session_id, None)
        if scheduled_task is not None:
            scheduled_task.cancel()
        await query.answer("Ход мафии зафиксирован.")
        await _announce_mafia_resolution(finalize_result)
        await broadcast_mafia_turn_update(
            finalize_result.snapshot,
            prefix_by_user_id={
                member.tg_user_id: "Команда мафии завершила выбор."
                for member in finalize_result.snapshot.members
            },
        )
        advance_result = await advance_after_mafia_resolution(finalize_result.snapshot.room_id)
        await launch_stage_advance(advance_result)
        return

    await query.answer("Готовность включена." if became_ready else "Готовность снята.")
    await broadcast_mafia_turn_update(snapshot)

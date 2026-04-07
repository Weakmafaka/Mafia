import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional

from aiogram.exceptions import TelegramBadRequest

from core.telegram import bot
from database.controllers.game_flow import DAY_VOTE_STAGE
from database.controllers.game_flow import StageAdvanceResult
from database.controllers.game_flow import StageSnapshot
from database.controllers.game_flow import finalize_generic_stage_on_timeout
from database.controllers.game_flow import set_stage_group_message_id
from game.classic_mafia.narrator import build_stage_opening_message
from database.controllers.room import get_user_room_snapshot
from handlers.game_rooms.day_vote_keyboards import day_vote_group_keyboard
from handlers.game_rooms.day_vote_views import build_day_vote_group_text
from handlers.game_rooms.stage_keyboards import stage_group_keyboard
from handlers.game_rooms.stage_views import build_stage_group_text
from handlers.game_rooms.views import broadcast_room_update
from utils.group_verifier import resolve_group_chat


_GENERIC_STAGE_TIMEOUT_TASKS: Dict[int, asyncio.Task] = {}


async def _resolve_group_chat_id(snapshot: StageSnapshot) -> Optional[int]:
    if snapshot.group_chat_id is not None:
        return int(snapshot.group_chat_id)
    if not snapshot.group_link:
        return None
    resolved = await resolve_group_chat(bot, snapshot.group_link)
    if not resolved.ok:
        return None
    return resolved.chat_id


async def send_group_stage_announcement(snapshot: StageSnapshot, text: str) -> None:
    chat_id = await _resolve_group_chat_id(snapshot)
    if chat_id is None:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except TelegramBadRequest:
        return


async def start_generic_stage_flow(snapshot: StageSnapshot, group_message: Optional[str] = None) -> None:
    chat_id = await _resolve_group_chat_id(snapshot)
    if chat_id is None:
        return

    try:
        if snapshot.stage == DAY_VOTE_STAGE:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=build_day_vote_group_text(
                    snapshot,
                    prefix=group_message or build_stage_opening_message(snapshot.stage, snapshot.night_number),
                ),
                reply_markup=day_vote_group_keyboard(snapshot),
            )
        else:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=build_stage_group_text(
                    snapshot,
                    prefix=group_message or build_stage_opening_message(snapshot.stage, snapshot.night_number),
                ),
                reply_markup=stage_group_keyboard(snapshot),
            )
    except TelegramBadRequest:
        return

    await set_stage_group_message_id(snapshot.game_session_id, sent_message.message_id)
    snapshot.group_message_id = sent_message.message_id
    _schedule_generic_timeout(snapshot)


def _schedule_generic_timeout(snapshot: StageSnapshot) -> None:
    current_task = _GENERIC_STAGE_TIMEOUT_TASKS.pop(snapshot.game_session_id, None)
    if current_task is not None:
        current_task.cancel()
    if snapshot.deadline_at is None:
        return

    async def _runner() -> None:
        try:
            if snapshot.deadline_at is None:
                return
            await asyncio.sleep(max(0, (snapshot.deadline_at - datetime.now(timezone.utc)).total_seconds()))
            advance_result = await finalize_generic_stage_on_timeout(snapshot.game_session_id)
            if advance_result is None:
                return
            await launch_stage_advance(advance_result)
        finally:
            _GENERIC_STAGE_TIMEOUT_TASKS.pop(snapshot.game_session_id, None)

    _GENERIC_STAGE_TIMEOUT_TASKS[snapshot.game_session_id] = asyncio.create_task(_runner())


async def launch_stage_advance(advance_result: StageAdvanceResult) -> None:
    if advance_result.next_stage_snapshot is not None:
        for tg_user_id, text in advance_result.private_messages.items():
            try:
                await bot.send_message(chat_id=tg_user_id, text=text)
            except TelegramBadRequest:
                continue
        if advance_result.next_stage_snapshot.stage == "mafia":
            from handlers.game_rooms.night_mafia import start_mafia_turn_flow

            await start_mafia_turn_flow(
                advance_result.next_stage_snapshot.room_id,
                group_message=advance_result.group_message,
            )
            return
        await start_generic_stage_flow(
            advance_result.next_stage_snapshot,
            group_message=advance_result.group_message,
        )
        return

    if advance_result.private_messages:
        for tg_user_id, text in advance_result.private_messages.items():
            try:
                await bot.send_message(chat_id=tg_user_id, text=text)
            except TelegramBadRequest:
                continue

    if advance_result.group_message and advance_result.victory_result is not None:
        if advance_result.victory_result.winners or advance_result.victory_result.losers:
            sample_user_id = (
                advance_result.victory_result.winners[0]
                if advance_result.victory_result.winners
                else advance_result.victory_result.losers[0]
            )
            snapshot = await get_user_room_snapshot(sample_user_id)
            if snapshot is not None:
                stage_like_snapshot = StageSnapshot(
                    room_id=snapshot.room_id,
                    room_title=snapshot.title,
                    room_code=snapshot.code,
                    group_link=snapshot.group_link,
                    group_chat_id=None,
                    game_session_id=0,
                    phase="finished",
                    stage="finished",
                    night_number=0,
                    deadline_at=None,
                    group_message_id=None,
                    actors=[],
                    targets=[],
                )
                await send_group_stage_announcement(stage_like_snapshot, advance_result.group_message)
                await broadcast_room_update(
                    snapshot,
                    prefix_by_user_id={player.tg_user_id: advance_result.group_message for player in snapshot.players},
                )

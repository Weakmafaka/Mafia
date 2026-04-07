from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from core.telegram import bot
from database.controllers.game_flow import (
    RoomControllerError,
    submit_day_vote_skip,
    submit_day_vote_target,
)
from handlers.game_rooms.day_vote_views import render_day_vote_group_message
from handlers.game_rooms.stage_runtime import launch_stage_advance

router = Router()


async def _close_vote_message(query: CallbackQuery, text: str) -> None:
    try:
        await bot.edit_message_text(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            text=text,
            reply_markup=None,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(F.data.startswith("day_vote_target_"))
async def callback_day_vote_target(query: CallbackQuery) -> None:
    try:
        target_tg_user_id = int(query.data.rsplit("_", 1)[1])
    except (TypeError, ValueError, IndexError):
        await query.answer("Не удалось определить цель голосования.", show_alert=True)
        return

    try:
        snapshot, advance_result = await submit_day_vote_target(query.from_user.id, target_tg_user_id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    if advance_result is not None:
        await query.answer("Последний голос принят.")
        await _close_vote_message(query, "Все голоса собраны. Ведущий подводит итоги...")
        await launch_stage_advance(advance_result)
        return

    await query.answer("Голос принят.")
    await render_day_vote_group_message(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        snapshot=snapshot,
    )


@router.callback_query(F.data == "day_vote_skip")
async def callback_day_vote_skip(query: CallbackQuery) -> None:
    try:
        snapshot, advance_result = await submit_day_vote_skip(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    if advance_result is not None:
        await query.answer("Последний голос принят.")
        await _close_vote_message(query, "Все голоса собраны. Ведущий подводит итоги...")
        await launch_stage_advance(advance_result)
        return

    await query.answer("Твой голос учтен.")
    await render_day_vote_group_message(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        snapshot=snapshot,
    )

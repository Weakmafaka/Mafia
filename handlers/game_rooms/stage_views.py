from datetime import datetime, timezone
from typing import Dict, Optional

from aiogram.exceptions import TelegramBadRequest

from core.telegram import bot
from database.controllers.game_flow import DAY_VOTE_STAGE
from database.controllers.game_flow import ROLE_STAGE_META
from database.controllers.game_flow import StageSnapshot
from database.controllers.game_flow import get_stage_action_message_targets
from handlers.game_rooms.stage_keyboards import stage_main_keyboard
from handlers.game_rooms.stage_keyboards import stage_group_keyboard


def _remaining_seconds(deadline_at) -> int:
    if deadline_at is None:
        return 0
    return max(0, int((deadline_at - datetime.now(timezone.utc)).total_seconds()))


def build_stage_text(snapshot: StageSnapshot, viewer_tg_user_id: int, prefix: Optional[str] = None) -> str:
    meta = ROLE_STAGE_META[snapshot.stage]
    viewer = next((item for item in snapshot.actors if item.tg_user_id == viewer_tg_user_id), None)
    lines = [
        "{}".format(meta["title"]),
        "Комната: {}".format(snapshot.room_title),
        "Ночь: {}".format(snapshot.night_number) if snapshot.phase == "night" else "День",
        "",
        "Участники этого этапа:",
    ]
    if snapshot.deadline_at is not None:
        lines.insert(3, "До автохода: {} сек.".format(_remaining_seconds(snapshot.deadline_at)))
    for index, actor in enumerate(snapshot.actors, start=1):
        choice = "пропуск" if actor.selected_skip else (actor.selected_target_name or "не выбрал")
        ready = "готов" if actor.is_ready else "не готов"
        lines.append("{}. {} - {} - {}".format(index, actor.display_name, choice, ready))

    if viewer is not None:
        lines.append("")
        viewer_choice = "пропуск" if viewer.selected_skip else (viewer.selected_target_name or "не выбрал")
        lines.append("Твой выбор: {}".format(viewer_choice))

    text = "\n".join(lines)
    return "{}\n\n{}".format(prefix, text) if prefix else text


def build_stage_group_text(snapshot: StageSnapshot, prefix: Optional[str] = None) -> str:
    meta = ROLE_STAGE_META[snapshot.stage]
    total_actors = len(snapshot.actors)
    selected_count = len(
        [
            actor
            for actor in snapshot.actors
            if actor.selected_skip or actor.selected_target_tg_user_id is not None
        ]
    )
    ready_count = len([actor for actor in snapshot.actors if actor.is_ready])
    lines = [
        meta["title"],
        "Ночь: {}".format(snapshot.night_number) if snapshot.phase == "night" else "День",
    ]
    if snapshot.deadline_at is not None:
        lines.append("Времени осталось: {} сек.".format(_remaining_seconds(snapshot.deadline_at)))
    lines.extend(
        [
            "",
            "Сейчас ход за этой ролью.",
            "",
            "Выбор сделали: {}/{}".format(selected_count, total_actors),
            "Подтвердили решение: {}/{}".format(ready_count, total_actors),
        ]
    )
    text = "\n".join(lines)
    return "{}\n\n{}".format(prefix, text) if prefix else text


async def render_stage_message(
    chat_id: int,
    message_id: int,
    snapshot: StageSnapshot,
    viewer_tg_user_id: int,
    prefix: Optional[str] = None,
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_stage_text(snapshot, viewer_tg_user_id, prefix=prefix),
            reply_markup=stage_main_keyboard(snapshot, viewer_tg_user_id),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def render_stage_group_message(
    chat_id: int,
    message_id: int,
    snapshot: StageSnapshot,
    prefix: Optional[str] = None,
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_stage_group_text(snapshot, prefix=prefix),
            reply_markup=stage_group_keyboard(snapshot),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def broadcast_stage_update(snapshot: StageSnapshot, prefix_by_user_id: Optional[Dict[int, str]] = None) -> None:
    if snapshot.group_message_id is not None and snapshot.group_chat_id is not None:
        prefix = None
        if prefix_by_user_id and prefix_by_user_id:
            prefix = next(iter(prefix_by_user_id.values()))
        await render_stage_group_message(
            chat_id=snapshot.group_chat_id,
            message_id=snapshot.group_message_id,
            snapshot=snapshot,
            prefix=prefix,
        )
        return

    targets = await get_stage_action_message_targets(snapshot.game_session_id, snapshot.stage)
    targets_by_user_id = {tg_user_id: message_id for tg_user_id, message_id in targets}
    for actor in snapshot.actors:
        message_id = targets_by_user_id.get(actor.tg_user_id)
        if not message_id:
            continue
        prefix = prefix_by_user_id.get(actor.tg_user_id) if prefix_by_user_id else None
        try:
            await render_stage_message(
                chat_id=actor.tg_user_id,
                message_id=message_id,
                snapshot=snapshot,
                viewer_tg_user_id=actor.tg_user_id,
                prefix=prefix,
            )
        except TelegramBadRequest:
            continue

from datetime import datetime, timezone
from typing import Dict, Optional

from aiogram.exceptions import TelegramBadRequest

from core.telegram import bot
from database.controllers.mafia_turn import MafiaTurnSnapshot
from handlers.game_rooms.night_keyboards import mafia_main_keyboard


def _remaining_seconds(deadline_at) -> int:
    if deadline_at is None:
        return 0
    remaining = int((deadline_at - datetime.now(timezone.utc)).total_seconds())
    return max(0, remaining)


def build_mafia_turn_text(snapshot: MafiaTurnSnapshot, viewer_tg_user_id: int, prefix: Optional[str] = None) -> str:
    selected_count = len(
        [
            member
            for member in snapshot.members
            if member.selected_skip or member.selected_target_tg_user_id is not None
        ]
    )
    ready_count = len([member for member in snapshot.members if member.is_ready])
    lines = [
        "Ночь {}. Ход мафии".format(snapshot.night_number),
        "Времени осталось: {} сек.".format(_remaining_seconds(snapshot.deadline_at)),
        "",
        "Мафия выбирает жертву.",
        "",
        "Выбор сделали: {}/{}".format(selected_count, len(snapshot.members)),
        "Подтвердили решение: {}/{}".format(ready_count, len(snapshot.members)),
    ]
    if snapshot.is_resolved:
        lines.append("")
        lines.append("Выбор мафии уже зафиксирован.")

    text = "\n".join(lines)
    return "{}\n\n{}".format(prefix, text) if prefix else text


async def render_mafia_turn_message(
    chat_id: int,
    message_id: int,
    snapshot: MafiaTurnSnapshot,
    viewer_tg_user_id: int,
    prefix: Optional[str] = None,
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_mafia_turn_text(snapshot, viewer_tg_user_id, prefix=prefix),
            reply_markup=mafia_main_keyboard(snapshot, viewer_tg_user_id),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def broadcast_mafia_turn_update(
    snapshot: MafiaTurnSnapshot,
    prefix_by_user_id: Optional[Dict[int, str]] = None,
) -> None:
    if snapshot.group_message_id is None or snapshot.group_chat_id is None:
        return
    prefix = None
    if prefix_by_user_id:
        prefix = next(iter(prefix_by_user_id.values()))
    await render_mafia_turn_message(
        chat_id=snapshot.group_chat_id,
        message_id=snapshot.group_message_id,
        snapshot=snapshot,
        viewer_tg_user_id=0,
        prefix=prefix,
    )

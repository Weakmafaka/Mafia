from typing import Dict, Optional

from aiogram.exceptions import TelegramBadRequest

from core.telegram import bot
from database.controllers.game_flow import StageSnapshot

from handlers.game_rooms.day_vote_keyboards import day_vote_group_keyboard


def _choice_label(actor) -> str:
    if actor.selected_skip:
        return "никого не изгонять"
    if actor.selected_target_name:
        return actor.selected_target_name
    return "еще не решил"


def _scoreboard_lines(snapshot: StageSnapshot) -> str:
    counts: Dict[str, int] = {}
    for actor in snapshot.actors:
        if not actor.is_ready:
            continue
        label = _choice_label(actor)
        counts[label] = counts.get(label, 0) + 1

    if not counts:
        return "Пока никто не отдал голос."

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    return "\n".join("- {}: {}".format(label, votes) for label, votes in ordered)


def build_day_vote_group_text(snapshot: StageSnapshot, prefix: Optional[str] = None) -> str:
    lines = [
        "Утреннее голосование",
        "После ночи {}".format(snapshot.night_number),
        "",
        "Каждый живой игрок должен назвать подозреваемого.",
        "Как только все голоса будут отданы, ведущий сразу объявит итог.",
        "",
        "Голоса:",
    ]
    for index, actor in enumerate(snapshot.actors, start=1):
        status = "голос отдан" if actor.is_ready else "еще молчит"
        lines.append("{}. {} — {} ({})".format(index, actor.display_name, _choice_label(actor), status))

    waiting = [actor.display_name for actor in snapshot.actors if not actor.is_ready]
    lines.extend([
        "",
        "Расклад голосов:",
        _scoreboard_lines(snapshot),
        "",
        "Осталось услышать: {}".format(", ".join(waiting) if waiting else "никого"),
    ])

    text = "\n".join(lines)
    return "{}\n\n{}".format(prefix, text) if prefix else text


async def render_day_vote_group_message(
    chat_id: int,
    message_id: int,
    snapshot: StageSnapshot,
    prefix: Optional[str] = None,
    with_keyboard: bool = True,
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_day_vote_group_text(snapshot, prefix=prefix),
            reply_markup=day_vote_group_keyboard(snapshot) if with_keyboard else None,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise

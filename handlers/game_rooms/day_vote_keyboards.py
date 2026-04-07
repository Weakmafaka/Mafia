from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.controllers.game_flow import StageSnapshot


def day_vote_group_keyboard(snapshot: StageSnapshot) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for target in snapshot.targets:
        if not target.is_alive:
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    text="Подозреваю: {}".format(target.display_name),
                    callback_data="day_vote_target_{}".format(target.tg_user_id),
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="Никого не изгонять", callback_data="day_vote_skip")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

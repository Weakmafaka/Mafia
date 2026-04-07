from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.controllers.mafia_turn import MafiaTurnSnapshot


def mafia_main_keyboard(snapshot: MafiaTurnSnapshot, viewer_tg_user_id: int) -> InlineKeyboardMarkup:
    if snapshot.is_resolved:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Ход зафиксирован", callback_data="mafia_turn_noop")],
            ]
        )

    buttons = [
        [
            InlineKeyboardButton(
                text="Убить игрока" if snapshot.single_mafia else "Проголосовать за убийство",
                callback_data="mafia_open_vote_targets",
            )
        ],
        [InlineKeyboardButton(text="Пропустить", callback_data="mafia_select_skip")],
        [InlineKeyboardButton(text="Подтвердить выбор", callback_data="mafia_ready_toggle")],
        [InlineKeyboardButton(text="Отозвать готовность", callback_data="mafia_ready_toggle")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def mafia_vote_targets_keyboard(snapshot: MafiaTurnSnapshot) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for target in snapshot.kill_targets:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=target.display_name,
                    callback_data="mafia_vote_target_{}".format(target.tg_user_id),
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="mafia_back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def mafia_visit_targets_keyboard(snapshot: MafiaTurnSnapshot, viewer_tg_user_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for target in snapshot.visit_targets:
        if target.tg_user_id == viewer_tg_user_id:
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    text=target.display_name,
                    callback_data="mafia_visit_target_{}".format(target.tg_user_id),
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="mafia_back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

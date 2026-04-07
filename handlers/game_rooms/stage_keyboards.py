from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.controllers.game_flow import DAY_VOTE_STAGE
from database.controllers.game_flow import ROLE_STAGE_META
from database.controllers.game_flow import StageSnapshot


def stage_main_keyboard(snapshot: StageSnapshot, viewer_tg_user_id: int) -> InlineKeyboardMarkup:
    actor = next((item for item in snapshot.actors if item.tg_user_id == viewer_tg_user_id), None)
    if actor is None:
        return InlineKeyboardMarkup(inline_keyboard=[])

    if actor.is_ready:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отозвать готовность", callback_data="stage_ready_toggle")],
            ]
        )

    has_choice = actor.selected_skip or actor.selected_target_tg_user_id is not None
    meta = ROLE_STAGE_META[snapshot.stage]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=meta["action_button"], callback_data="stage_open_targets")],
            [InlineKeyboardButton(text=meta["skip_text"], callback_data="stage_select_skip")],
            [
                InlineKeyboardButton(
                    text="Я сделал свой выбор" if has_choice else "Сначала выбери действие",
                    callback_data="stage_ready_toggle" if has_choice else "stage_ready_blocked",
                )
            ],
        ]
    )


def stage_target_keyboard(snapshot: StageSnapshot, viewer_tg_user_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for target in snapshot.targets:
        if not target.is_alive and snapshot.stage != "ghost":
            continue
        if snapshot.stage != DAY_VOTE_STAGE and snapshot.stage != "ghost" and target.tg_user_id == viewer_tg_user_id:
            continue
        buttons.append(
            [InlineKeyboardButton(text=target.display_name, callback_data="stage_target_{}".format(target.tg_user_id))]
        )
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="stage_back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def stage_group_keyboard(snapshot: StageSnapshot) -> InlineKeyboardMarkup:
    meta = ROLE_STAGE_META[snapshot.stage]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=meta["action_button"], callback_data="stage_open_targets")],
            [InlineKeyboardButton(text=meta["skip_text"], callback_data="stage_select_skip")],
            [InlineKeyboardButton(text="Подтвердить выбор", callback_data="stage_ready_toggle")],
            [InlineKeyboardButton(text="Отозвать готовность", callback_data="stage_ready_toggle")],
        ]
    )

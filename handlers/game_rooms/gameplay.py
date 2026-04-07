from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from core.telegram import bot
from database.controllers.game_start import RoleAcknowledgeResult
from database.controllers.game_start import acknowledge_role_for_user
from database.controllers.game_start import start_game_for_owner
from database.controllers.room import RoomControllerError
from database.controllers.room import get_user_room_snapshot
from handlers.game_rooms.helpers import is_owner
from handlers.game_rooms.stage_runtime import launch_stage_advance
from handlers.game_rooms.views import broadcast_room_update
from game.classic_mafia.briefing import build_role_brief_text
from game.classic_mafia.briefing import get_role_card_path
from utils.group_verifier import verify_user_in_group

router = Router()


def role_ack_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Ознакомился", callback_data="game_role_ack")]]
    )


@router.callback_query(F.data == "room_owner_start")
async def callback_room_owner_start(query: CallbackQuery) -> None:
    snapshot = await get_user_room_snapshot(query.from_user.id)
    if snapshot is None:
        await query.answer("Комната недоступна.", show_alert=True)
        return
    if not is_owner(snapshot, query.from_user.id):
        await query.answer("Только владелец может начать игру.", show_alert=True)
        return
    if snapshot.game_status != "lobby":
        await query.answer("Игра в этой комнате уже началась.", show_alert=True)
        return
    if not snapshot.can_start:
        await query.answer(
            "Нельзя начать игру: нужен полный состав и все игроки должны быть готовы.",
            show_alert=True,
        )
        return

    for player in snapshot.players:
        membership = await verify_user_in_group(bot, snapshot.group_link or "", player.tg_user_id)
        if not membership.ok:
            await query.answer(
                'Игрок "{}" не найден в групповом чате. Исправь состав комнаты и попробуй снова.'.format(
                    player.display_name,
                ),
                show_alert=True,
            )
            return

    try:
        start_result = await start_game_for_owner(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    failed_players = []
    for assignment in start_result.assignments:
        try:
            await bot.send_photo(
                chat_id=assignment.tg_user_id,
                photo=FSInputFile(str(get_role_card_path(assignment.role_key))),
                caption=build_role_brief_text(assignment.role_key),
                reply_markup=role_ack_keyboard(),
            )
        except TelegramBadRequest:
            failed_players.append(assignment.display_name)

    prefix = "Игра началась. Карточки ролей отправлены в личные сообщения."
    if failed_players:
        prefix = (
            "Игра началась, но некоторым игрокам не удалось отправить карточку роли: {}."
        ).format(", ".join(failed_players))

    await query.answer("Игра началась.")
    await broadcast_room_update(
        start_result.snapshot,
        prefix_by_user_id={player.tg_user_id: prefix for player in start_result.snapshot.players},
    )


@router.callback_query(F.data == "room_owner_start_blocked")
async def callback_room_owner_start_blocked(query: CallbackQuery) -> None:
    await query.answer(
        "Игра не может начаться, пока не собран полный состав и не готовы все игроки.",
        show_alert=True,
    )


@router.callback_query(F.data == "game_role_ack")
async def callback_game_role_ack(query: CallbackQuery) -> None:
    try:
        ack_result: RoleAcknowledgeResult = await acknowledge_role_for_user(query.from_user.id)
    except RoomControllerError as exc:
        await query.answer(str(exc), show_alert=True)
        return

    caption = query.message.caption or ""
    if "Статус: ты ознакомился с ролью." not in caption:
        caption = "{}\n\nСтатус: ты ознакомился с ролью.".format(caption)
        try:
            await bot.edit_message_caption(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                caption=caption,
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass

    await query.answer("Отлично, роль подтверждена.")
    await broadcast_room_update(ack_result.snapshot)
    if ack_result.all_roles_acknowledged:
        from database.controllers.game_flow import build_next_stage_after_role_ack

        try:
            advance_result = await build_next_stage_after_role_ack(ack_result.snapshot.room_id)
        except RoomControllerError:
            return
        await launch_stage_advance(advance_result)

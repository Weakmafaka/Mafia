from typing import Dict, Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

from core.telegram import bot
from database.controllers.room import RoomSnapshot
from database.controllers.room_roles import RoomRoleConfigSnapshot
from database.controllers.ui_state import get_room_message_targets, set_menu_message_id
from game.modes import GameMode
from game.modes import game_mode_label
from handlers.common import edit_menu_caption
from handlers.game_rooms.helpers import is_owner, mask_password, short_name, viewer_ready
from handlers.game_rooms.keyboards import (
    create_draft_keyboard,
    join_input_keyboard,
    owner_custom_role_settings_keyboard,
    owner_game_settings_keyboard,
    owner_room_keyboard,
    participant_room_keyboard,
    retry_group_check_keyboard,
    start_game_keyboard,
    create_visibility_keyboard,
)
from handlers.game_rooms.states import DEFAULT_ROOM_PLAYERS
from utils.group_verifier import verify_group_link


def build_game_menu_text(prefix: Optional[str] = None) -> str:
    body = "Игровое меню\n\nВыбери: создать комнату или присоединиться к существующей."
    return "{}\n\n{}".format(prefix, body) if prefix else body


def build_create_draft_text(title: str, max_players: int, chat_link: str, password: str) -> str:
    return (
        "Конструктор комнаты\n\n"
        "Название: {}\n"
        "Игроков: {}\n"
        "Тип: Приватная\n"
        "Пароль: {}\n"
        "Чат: {}\n\n"
        "Настрой параметры и нажми «Создать комнату»."
    ).format(title, max_players, mask_password(password), chat_link)


def build_room_text(snapshot: RoomSnapshot, viewer_tg_user_id: int, prefix: Optional[str] = None) -> str:
    players_lines = []
    for index, player in enumerate(snapshot.players, start=1):
        if snapshot.game_status == "finished":
            status = "Был в игре"
        elif snapshot.game_status == "started":
            status = "Ознакомился с ролью" if player.role_acknowledged else "Не ознакомился с ролью"
        else:
            status = "Готов" if player.is_ready else "Не готов"
        owner_mark = " (владелец)" if player.is_owner else ""
        players_lines.append(
            "{}. {}{} - {}".format(index, short_name(player.display_name), owner_mark, status)
        )

    lines = [
        "Комната: {}".format(snapshot.title),
        "Код: {}".format(snapshot.code),
        "Тип: {}".format("Приватная" if snapshot.is_private else "Публичная"),
        "Режим: {}".format(game_mode_label(snapshot.game_mode)),
        "Статус: {}".format(
            "Игра завершена"
            if snapshot.game_status == "finished"
            else ("Игра идет" if snapshot.game_status == "started" else "Ожидание игроков")
        ),
        "Игроки: {}/{}".format(snapshot.players_count, snapshot.max_players),
        "Ссылка на чат: {}".format(snapshot.group_link or "-"),
        "",
        "Участники:",
        "\n".join(players_lines) if players_lines else "Пока нет игроков",
        "",
        (
            "Партия завершена."
            if snapshot.game_status == "finished"
            else
            "Ознакомились с ролью: {}/{}".format(
                snapshot.role_acknowledged_players_count,
                snapshot.players_count,
            )
            if snapshot.game_status == "started"
            else "Готовы: {}/{}".format(snapshot.ready_players_count, snapshot.players_count)
        ),
    ]

    if viewer_tg_user_id == snapshot.owner_tg_user_id and snapshot.game_status == "lobby":
        lines.append("Можно начать: {}".format("Да" if snapshot.can_start else "Нет"))

    text = "\n".join(lines)
    return "{}\n\n{}".format(prefix, text) if prefix else text


async def render_room_lobby(
    chat_id: int,
    message_id: int,
    viewer_tg_user_id: int,
    snapshot: RoomSnapshot,
    prefix: Optional[str] = None,
) -> None:
    text = build_room_text(snapshot, viewer_tg_user_id, prefix=prefix)
    keyboard = owner_room_keyboard(snapshot) if is_owner(snapshot, viewer_tg_user_id) else participant_room_keyboard(
        snapshot,
        viewer_ready(snapshot, viewer_tg_user_id),
    )
    await edit_menu_caption(chat_id=chat_id, message_id=message_id, text=text, keyboard=keyboard)
    await set_menu_message_id(viewer_tg_user_id, message_id)


async def render_game_menu(chat_id: int, message_id: int, prefix: Optional[str] = None) -> None:
    await edit_menu_caption(
        chat_id=chat_id,
        message_id=message_id,
        text=build_game_menu_text(prefix),
        keyboard=start_game_keyboard(),
    )


async def broadcast_room_update(
    snapshot: RoomSnapshot,
    prefix_by_user_id: Optional[Dict[int, str]] = None,
    skip_user_ids: Optional[set] = None,
) -> None:
    targets = await get_room_message_targets(snapshot.room_id)
    message_targets = {tg_user_id: message_id for tg_user_id, message_id in targets}

    for player in snapshot.players:
        if skip_user_ids and player.tg_user_id in skip_user_ids:
            continue
        message_id = message_targets.get(player.tg_user_id)
        if not message_id:
            continue

        prefix = prefix_by_user_id.get(player.tg_user_id) if prefix_by_user_id else None
        try:
            await render_room_lobby(
                chat_id=player.tg_user_id,
                message_id=message_id,
                viewer_tg_user_id=player.tg_user_id,
                snapshot=snapshot,
                prefix=prefix,
            )
        except TelegramBadRequest:
            continue


async def render_create_draft(chat_id: int, message_id: int, state: FSMContext, prefix: Optional[str] = None) -> None:
    data = await state.get_data()
    draft_title = data.get("create_draft_title", "Новая комната")
    draft_players = int(data.get("create_draft_max_players", DEFAULT_ROOM_PLAYERS))
    draft_link = data.get("create_draft_chat_link", "-")
    draft_password = data.get("create_draft_password", "")
    text = build_create_draft_text(
        title=draft_title,
        max_players=draft_players,
        chat_link=draft_link,
        password=draft_password,
    )
    if prefix:
        text = "{}\n\n{}".format(prefix, text)
    await edit_menu_caption(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        keyboard=create_draft_keyboard(draft_players),
    )


def build_owner_game_settings_text(snapshot: RoomSnapshot, prefix: Optional[str] = None) -> str:
    is_classic = snapshot.game_mode == GameMode.CLASSIC.value
    mode_text = game_mode_label(snapshot.game_mode)
    role_settings_text = (
        "В классике роли фиксированы и недоступны для ручной настройки."
        if is_classic
        else "В кастоме владелец сможет настраивать состав ролей вручную."
    )
    text = (
        "Настройки игры\n\n"
        "Комната: {}\n"
        "Текущий формат: {}\n\n"
        "{}"
    ).format(snapshot.title, mode_text, role_settings_text)
    return "{}\n\n{}".format(prefix, text) if prefix else text


async def render_owner_game_settings(
    chat_id: int,
    message_id: int,
    snapshot: RoomSnapshot,
    prefix: Optional[str] = None,
) -> None:
    await edit_menu_caption(
        chat_id=chat_id,
        message_id=message_id,
        text=build_owner_game_settings_text(snapshot, prefix=prefix),
        keyboard=owner_game_settings_keyboard(snapshot.game_mode),
    )
    await set_menu_message_id(snapshot.owner_tg_user_id, message_id)


def build_owner_custom_role_settings_text(
    snapshot: RoomRoleConfigSnapshot,
    prefix: Optional[str] = None,
) -> str:
    text = (
        "Настройка ролей\n\n"
        "Комната: {}\n"
        "Формат: Кастом\n"
        "Назначено ролей: {}/{}\n"
        "Свободно мест: {}\n\n"
        "Если у роли 0 игроков, эта роль не участвует в партии."
    ).format(
        snapshot.room_title,
        snapshot.total_assigned,
        snapshot.max_players,
        snapshot.remaining_slots,
    )
    return "{}\n\n{}".format(prefix, text) if prefix else text


async def render_owner_custom_role_settings(
    chat_id: int,
    message_id: int,
    snapshot: RoomRoleConfigSnapshot,
    owner_tg_user_id: int,
    prefix: Optional[str] = None,
) -> None:
    await edit_menu_caption(
        chat_id=chat_id,
        message_id=message_id,
        text=build_owner_custom_role_settings_text(snapshot, prefix=prefix),
        keyboard=owner_custom_role_settings_keyboard(snapshot),
    )
    await set_menu_message_id(owner_tg_user_id, message_id)


async def render_group_check_error(
    chat_id: int,
    message_id: int,
    verification_message: str,
    allow_recheck: bool,
) -> None:
    suffix = (
        "Исправь настройки группы и нажми «Проверить снова»."
        if allow_recheck
        else "После исправления отправь ссылку снова."
    )
    await edit_menu_caption(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            "Проверка группы не пройдена.\n\n"
            "{}\n\n"
            "{}"
        ).format(verification_message, suffix),
        keyboard=retry_group_check_keyboard() if allow_recheck else join_input_keyboard(),
    )


async def verify_pending_group_link(
    chat_id: int,
    message_id: int,
    state: FSMContext,
    chat_link: str,
) -> bool:
    verification = await verify_group_link(bot, chat_link)
    await state.update_data(create_draft_chat_link_candidate=chat_link)

    if not verification.ok:
        await render_group_check_error(
            chat_id=chat_id,
            message_id=message_id,
            verification_message=verification.message,
            allow_recheck=verification.reason in ("bot_not_admin", "bot_cannot_access_chat"),
        )
        return False

    await state.update_data(create_draft_chat_link=verification.normalized_link)
    await state.update_data(create_draft_group_chat_id=verification.chat_id)
    await state.update_data(create_draft_chat_title=verification.chat_title)
    await state.update_data(create_draft_chat_link_candidate=verification.normalized_link)
    await state.set_state(None)
    await edit_menu_caption(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            "Создание комнаты\n\n"
            "{}\n\n"
            "Шаг 3 из 4.\n"
            "Выбери тип комнаты."
        ).format(verification.message),
        keyboard=create_visibility_keyboard(),
    )
    return True

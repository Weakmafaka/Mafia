from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.controllers.room import RoomSnapshot
from database.controllers.room_roles import RoomRoleConfigSnapshot
from game.modes import GameMode
from game.modes import game_mode_label


def start_game_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Создать игру", callback_data="game_create"),
                InlineKeyboardButton(text="Присоединиться к игре", callback_data="game_join"),
            ],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def join_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Присоединиться по коду", callback_data="game_join_by_code")],
            [InlineKeyboardButton(text="Публичные комнаты (скоро)", callback_data="game_join_public_disabled")],
            [InlineKeyboardButton(text="К меню игры", callback_data="room_back_to_start")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def join_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="К меню игры", callback_data="room_back_to_start")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def retry_group_check_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Проверить снова", callback_data="create_chat_link_recheck")],
            [InlineKeyboardButton(text="Отправить другую ссылку", callback_data="create_chat_link_change")],
            [InlineKeyboardButton(text="К меню игры", callback_data="room_back_to_start")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def create_visibility_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Приватная", callback_data="create_visibility_private")],
            [InlineKeyboardButton(text="Публичная (скоро)", callback_data="create_visibility_public_disabled")],
            [InlineKeyboardButton(text="К меню игры", callback_data="room_back_to_start")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def create_draft_keyboard(max_players: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀", callback_data="create_players_dec"),
                InlineKeyboardButton(text=str(max_players), callback_data="room_noop"),
                InlineKeyboardButton(text="▶", callback_data="create_players_inc"),
            ],
            [InlineKeyboardButton(text="Настройки игры (после создания)", callback_data="create_game_settings_stub")],
            [InlineKeyboardButton(text="Настройки комнаты", callback_data="create_settings_open")],
            [InlineKeyboardButton(text="Создать комнату", callback_data="create_finalize")],
            [InlineKeyboardButton(text="К меню игры", callback_data="room_back_to_start")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def create_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сменить название", callback_data="create_settings_change_name")],
            [InlineKeyboardButton(text="Сменить пароль", callback_data="create_settings_change_password")],
            [InlineKeyboardButton(text="Назад к конструктору", callback_data="create_settings_back")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def owner_room_keyboard(snapshot: RoomSnapshot) -> InlineKeyboardMarkup:
    if snapshot.game_status == "finished":
        return finished_room_keyboard(snapshot)
    if snapshot.game_status == "started":
        return owner_started_room_keyboard(snapshot)

    can_start = snapshot.can_start
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀", callback_data="room_owner_dec_players"),
                InlineKeyboardButton(text=str(snapshot.max_players), callback_data="room_noop"),
                InlineKeyboardButton(text="▶", callback_data="room_owner_inc_players"),
            ],
            [InlineKeyboardButton(text="Настройки игры", callback_data="room_owner_game_settings_open")],
            [InlineKeyboardButton(text="Настройки комнаты", callback_data="room_owner_settings_open")],
            [InlineKeyboardButton(text="Кикнуть игрока", callback_data="room_owner_kick_open")],
            [
                InlineKeyboardButton(
                    text="Начать игру" if can_start else "Начать игру (нужен полный состав)",
                    callback_data="room_owner_start" if can_start else "room_owner_start_blocked",
                )
            ],
            [InlineKeyboardButton(text="Выйти", callback_data="room_leave")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def participant_room_keyboard(snapshot: RoomSnapshot, viewer_is_ready: bool) -> InlineKeyboardMarkup:
    if snapshot.game_status == "finished":
        return finished_room_keyboard(snapshot)
    if snapshot.game_status == "started":
        return participant_started_room_keyboard(snapshot)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Игроки: {}/{}".format(snapshot.players_count, snapshot.max_players),
                    callback_data="room_noop",
                )
            ],
            [InlineKeyboardButton(text="Режим: {}".format(game_mode_label(snapshot.game_mode)), callback_data="room_noop")],
            [
                InlineKeyboardButton(
                    text="Приготовиться" if not viewer_is_ready else "Отменить готовность",
                    callback_data="room_toggle_ready",
                )
            ],
            [InlineKeyboardButton(text="Выйти", callback_data="room_leave")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def owner_started_room_keyboard(snapshot: RoomSnapshot) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Ознакомились с ролью: {}/{}".format(
                        snapshot.role_acknowledged_players_count,
                        snapshot.players_count,
                    ),
                    callback_data="room_noop",
                )
            ],
            [InlineKeyboardButton(text="Игра началась", callback_data="room_noop")],
            [InlineKeyboardButton(text="Выйти", callback_data="room_leave")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def participant_started_room_keyboard(snapshot: RoomSnapshot) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Ознакомились с ролью: {}/{}".format(
                        snapshot.role_acknowledged_players_count,
                        snapshot.players_count,
                    ),
                    callback_data="room_noop",
                )
            ],
            [InlineKeyboardButton(text="Игра началась", callback_data="room_noop")],
            [InlineKeyboardButton(text="Выйти", callback_data="room_leave")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def finished_room_keyboard(snapshot: RoomSnapshot) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Игра завершена", callback_data="room_noop")],
            [InlineKeyboardButton(text="Выйти", callback_data="room_leave")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def owner_room_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сменить название", callback_data="room_owner_settings_change_name")],
            [InlineKeyboardButton(text="Сменить пароль", callback_data="room_owner_settings_change_password")],
            [InlineKeyboardButton(text="Назад к комнате", callback_data="room_owner_settings_back")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def owner_room_reduce_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Кикнуть игрока", callback_data="room_owner_kick_open")],
            [InlineKeyboardButton(text="Назад к комнате", callback_data="room_owner_kick_cancel")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def owner_kick_players_keyboard(snapshot: RoomSnapshot) -> InlineKeyboardMarkup:
    buttons = []
    for player in snapshot.players:
        if player.is_owner:
            continue
        buttons.append(
            [InlineKeyboardButton(text=player.display_name, callback_data="room_owner_kick_select_{}".format(player.tg_user_id))]
        )

    buttons.append([InlineKeyboardButton(text="Назад к комнате", callback_data="room_owner_kick_cancel")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def owner_game_settings_keyboard(game_mode: str) -> InlineKeyboardMarkup:
    is_classic = game_mode == GameMode.CLASSIC.value
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=("• Классика" if is_classic else "Классика"),
                    callback_data="room_owner_game_mode_classic",
                ),
                InlineKeyboardButton(
                    text=("• Кастом" if not is_classic else "Кастом"),
                    callback_data="room_owner_game_mode_custom",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Настроить роли"
                    if game_mode == GameMode.CUSTOM.value
                    else "Настройка ролей недоступна",
                    callback_data="room_owner_game_roles_open"
                    if game_mode == GameMode.CUSTOM.value
                    else "room_owner_game_roles_blocked",
                )
            ],
            [InlineKeyboardButton(text="Назад к комнате", callback_data="room_owner_game_settings_back")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def owner_custom_role_settings_keyboard(snapshot: RoomRoleConfigSnapshot) -> InlineKeyboardMarkup:
    buttons = []
    for role in snapshot.roles:
        buttons.append(
            [
                InlineKeyboardButton(text="-", callback_data="room_owner_role_dec_{}".format(role.role_key)),
                InlineKeyboardButton(
                    text="{}: {}".format(role.role_name, role.count),
                    callback_data="room_noop",
                ),
                InlineKeyboardButton(text="+", callback_data="room_owner_role_inc_{}".format(role.role_key)),
            ]
        )

    buttons.append([InlineKeyboardButton(text="Назад к настройкам игры", callback_data="room_owner_game_settings_open")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

import random
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import func, select, update

from database.database import db
from database.controllers.game_session import ensure_game_session_for_room
from database.controllers.game_flow import initialize_game_player_states
from database.models.role import Role
from database.models.room import Room
from database.models.room_role_config import RoomRoleConfig
from database.models.user import User
from game.classic_mafia import build_classic_role_list
from game.classic_mafia.roles import CLASSIC_ROLE_SPECS_BY_KEY
from game.modes import GameMode

from .room import InvalidRoomConfigError
from .room import RoomControllerError
from .room import RoomNotFoundError
from .room import RoomSnapshot
from .room import _build_room_snapshot


@dataclass
class PlayerRoleAssignment:
    tg_user_id: int
    display_name: str
    role_id: int
    role_key: str
    role_name: str


@dataclass
class GameStartResult:
    snapshot: RoomSnapshot
    assignments: List[PlayerRoleAssignment]


@dataclass
class RoleAcknowledgeResult:
    snapshot: RoomSnapshot
    all_roles_acknowledged: bool


async def _get_owner_room_for_start(session, owner_tg_user_id: int) -> Room:
    room = await session.scalar(
        select(Room)
        .where(
            Room.owner_tg_user_id == owner_tg_user_id,
            Room.online.is_(True),
        )
        .with_for_update()
    )
    if room is None:
        raise RoomNotFoundError("Активная комната владельца не найдена.")
    if room.game_status != "lobby":
        raise RoomControllerError("Игра в этой комнате уже началась.")
    return room


async def _get_room_users_with_lock(session, room_id: int) -> List[User]:
    users = (
        await session.scalars(
            select(User)
            .where(User.room_id == room_id)
            .order_by(User.id.asc())
            .with_for_update()
        )
    ).all()
    return list(users)


async def _build_custom_role_list(session, room: Room, players_count: int) -> List[str]:
    config_rows = (
        await session.scalars(
            select(RoomRoleConfig).where(RoomRoleConfig.room_id == room.id)
        )
    ).all()
    counts_by_role = {row.role_key: int(row.count) for row in config_rows if int(row.count) > 0}
    role_keys: List[str] = []
    for role_key, count in counts_by_role.items():
        if role_key not in CLASSIC_ROLE_SPECS_BY_KEY:
            raise InvalidRoomConfigError("В кастомной настройке найдена неизвестная роль.")
        role_keys.extend([role_key] * count)

    if len(role_keys) != players_count:
        raise InvalidRoomConfigError(
            "Для кастома должно быть настроено ровно {} ролей. Сейчас настроено {}.".format(
                players_count,
                len(role_keys),
            )
        )
    return role_keys


async def _build_role_assignments_for_room(session, room: Room, players_count: int) -> List[str]:
    if room.game_mode == GameMode.CLASSIC.value:
        return build_classic_role_list(players_count)
    if room.game_mode == GameMode.CUSTOM.value:
        return await _build_custom_role_list(session, room, players_count)
    raise InvalidRoomConfigError("Неизвестный формат игры.")


async def start_game_for_owner(owner_tg_user_id: int) -> GameStartResult:
    async with db() as session:
        room = await _get_owner_room_for_start(session, owner_tg_user_id)
        users = await _get_room_users_with_lock(session, room.id)
        players_count = len(users)

        if players_count != room.max_players:
            raise RoomControllerError("Нельзя начать игру: состав комнаты еще не полный.")
        if any(not user.room_is_ready and user.tg_user_id != room.owner_tg_user_id for user in users):
            raise RoomControllerError("Нельзя начать игру: не все игроки готовы.")

        role_keys = await _build_role_assignments_for_room(session, room, players_count)
        random.shuffle(role_keys)

        roles = (
            await session.scalars(
                select(Role).where(Role.key.in_(role_keys))
            )
        ).all()
        roles_by_key = {role.key: role for role in roles}

        assignments: List[PlayerRoleAssignment] = []
        for user, role_key in zip(users, role_keys):
            role = roles_by_key.get(role_key)
            if role is None:
                raise RoomControllerError("Не найдена роль '{}' в таблице role.".format(role_key))
            spec = CLASSIC_ROLE_SPECS_BY_KEY.get(role_key)
            if spec is None:
                raise RoomControllerError("Не найдена спецификация роли '{}'.".format(role_key))

            user.role_id = role.id
            user.current_role_key = role_key
            user.role_acknowledged = False
            assignments.append(
                PlayerRoleAssignment(
                    tg_user_id=user.tg_user_id,
                    display_name=user.nickname or user.username or user.first_name or str(user.tg_user_id),
                    role_id=role.id,
                    role_key=role_key,
                    role_name=spec.name,
                )
            )

        room.game_status = "started"
        game_session = await ensure_game_session_for_room(session, room.id)
        await initialize_game_player_states(session, game_session.id, users)
        await session.execute(update(Room).where(Room.id == room.id).values(last_activity_at=func.now()))
        await session.flush()
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return GameStartResult(snapshot=snapshot, assignments=assignments)


async def acknowledge_role_for_user(tg_user_id: int) -> RoleAcknowledgeResult:
    async with db() as session:
        user = await session.scalar(
            select(User).where(User.tg_user_id == tg_user_id).with_for_update()
        )
        if user is None or user.room_id is None:
            raise RoomNotFoundError("Пользователь не состоит в активной комнате.")

        room = await session.scalar(
            select(Room)
            .where(
                Room.id == user.room_id,
                Room.online.is_(True),
            )
            .with_for_update()
        )
        if room is None or room.game_status != "started":
            raise RoomControllerError("Игра для этой комнаты еще не началась.")

        user.role_acknowledged = True
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return RoleAcknowledgeResult(
            snapshot=snapshot,
            all_roles_acknowledged=snapshot.all_roles_acknowledged,
        )

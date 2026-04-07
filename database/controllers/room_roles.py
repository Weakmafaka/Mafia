from dataclasses import dataclass
from typing import List

from sqlalchemy import func, select, update

from database.database import db
from database.models.room import Room
from database.models.room_role_config import RoomRoleConfig
from game.classic_mafia.roles import CLASSIC_ROLE_SPECS
from game.classic_mafia.roles import CLASSIC_ROLE_SPECS_BY_KEY
from game.modes import GameMode

from .room import InvalidRoomConfigError
from .room import NotRoomOwnerError
from .room import RoomControllerError
from .room import RoomNotFoundError


@dataclass
class RoleCountSnapshot:
    role_key: str
    role_name: str
    count: int


@dataclass
class RoomRoleConfigSnapshot:
    room_id: int
    room_title: str
    game_mode: str
    max_players: int
    total_assigned: int
    remaining_slots: int
    roles: List[RoleCountSnapshot]


def _validate_role_key(role_key: str) -> str:
    normalized = (role_key or "").strip().lower()
    if normalized not in CLASSIC_ROLE_SPECS_BY_KEY:
        raise InvalidRoomConfigError("Неизвестная роль.")
    return normalized


async def _touch_room(session, room_id: int) -> None:
    await session.execute(
        update(Room).where(Room.id == room_id).values(last_activity_at=func.now())
    )


async def _get_owner_room_for_role_config(session, owner_tg_user_id: int) -> Room:
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
    if room.game_mode != GameMode.CUSTOM.value:
        raise NotRoomOwnerError("Настройка ролей доступна только в режиме Кастом.")
    return room


async def _build_room_role_config_snapshot(session, room: Room) -> RoomRoleConfigSnapshot:
    config_rows = (
        await session.scalars(
            select(RoomRoleConfig).where(RoomRoleConfig.room_id == room.id)
        )
    ).all()
    counts_by_role = {row.role_key: int(row.count) for row in config_rows}

    roles = [
        RoleCountSnapshot(
            role_key=spec.key.value,
            role_name=spec.name,
            count=counts_by_role.get(spec.key.value, 0),
        )
        for spec in CLASSIC_ROLE_SPECS
    ]
    total_assigned = sum(role.count for role in roles)
    return RoomRoleConfigSnapshot(
        room_id=room.id,
        room_title=room.title,
        game_mode=room.game_mode,
        max_players=room.max_players,
        total_assigned=total_assigned,
        remaining_slots=max(room.max_players - total_assigned, 0),
        roles=roles,
    )


async def get_custom_role_config_for_owner(owner_tg_user_id: int) -> RoomRoleConfigSnapshot:
    async with db() as session:
        room = await _get_owner_room_for_role_config(session, owner_tg_user_id)
        return await _build_room_role_config_snapshot(session, room)


async def get_room_custom_role_total(session, room_id: int) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(RoomRoleConfig.count), 0)).where(RoomRoleConfig.room_id == room_id)
    )
    return int(total or 0)


async def update_custom_role_count_for_owner(
    owner_tg_user_id: int,
    role_key: str,
    delta: int,
) -> RoomRoleConfigSnapshot:
    normalized_role_key = _validate_role_key(role_key)
    if delta == 0:
        raise InvalidRoomConfigError("Изменение количества роли должно быть не нулевым.")

    async with db() as session:
        room = await _get_owner_room_for_role_config(session, owner_tg_user_id)
        config_row = await session.scalar(
            select(RoomRoleConfig)
            .where(
                RoomRoleConfig.room_id == room.id,
                RoomRoleConfig.role_key == normalized_role_key,
            )
            .with_for_update()
        )

        current_count = int(config_row.count) if config_row is not None else 0
        new_count = max(0, current_count + delta)
        current_total = await get_room_custom_role_total(session, room.id)
        new_total = current_total - current_count + new_count

        if new_total > room.max_players:
            raise InvalidRoomConfigError(
                "Нельзя назначить больше ролей, чем мест в комнате ({}).".format(room.max_players)
            )

        if config_row is None and new_count > 0:
            session.add(
                RoomRoleConfig(
                    room_id=room.id,
                    role_key=normalized_role_key,
                    count=new_count,
                )
            )
        elif config_row is not None:
            config_row.count = new_count

        await _touch_room(session, room.id)
        await session.flush()
        snapshot = await _build_room_role_config_snapshot(session, room)
        await session.commit()
        return snapshot

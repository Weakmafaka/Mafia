import random
import string
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import delete, func, select, text, update

from database.database import db
from database.models.game_action import GameAction
from database.models.game_player_state import GamePlayerState
from database.models.game_session import GameSession
from database.models.mafia_turn_action import MafiaTurnAction
from database.models.room import Room
from database.models.room_role_config import RoomRoleConfig
from database.models.user import User
from game.modes import GameMode

ROOM_CODE_LENGTH = 6
ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits
MIN_ROOM_PLAYERS = 5
MAX_ROOM_PLAYERS = 11


class RoomControllerError(Exception):
    pass


class RoomNotFoundError(RoomControllerError):
    pass


class UserAlreadyInRoomError(RoomControllerError):
    def __init__(self, room_snapshot: "RoomSnapshot"):
        super().__init__("Пользователь уже состоит в другой комнате.")
        self.room_snapshot = room_snapshot


class InvalidRoomPasswordError(RoomControllerError):
    pass


class RoomIsFullError(RoomControllerError):
    pass


class NotRoomOwnerError(RoomControllerError):
    pass


class InvalidRoomConfigError(RoomControllerError):
    pass


@dataclass
class RoomPlayerSnapshot:
    tg_user_id: int
    display_name: str
    is_ready: bool
    is_owner: bool
    role_acknowledged: bool


@dataclass
class RoomSnapshot:
    room_id: int
    code: str
    title: str
    is_private: bool
    game_mode: str
    game_status: str
    max_players: int
    owner_tg_user_id: int
    group_link: Optional[str]
    players: List[RoomPlayerSnapshot]

    @property
    def players_count(self) -> int:
        return len(self.players)

    @property
    def ready_players_count(self) -> int:
        return len([player for player in self.players if player.is_ready])

    @property
    def all_ready(self) -> bool:
        return self.players_count > 0 and self.ready_players_count == self.players_count

    @property
    def role_acknowledged_players_count(self) -> int:
        return len([player for player in self.players if player.role_acknowledged])

    @property
    def all_roles_acknowledged(self) -> bool:
        return self.players_count > 0 and self.role_acknowledged_players_count == self.players_count

    @property
    def is_full(self) -> bool:
        return self.players_count >= self.max_players

    @property
    def can_start(self) -> bool:
        return self.game_status == "lobby" and self.is_full and self.all_ready


@dataclass
class LeaveRoomResult:
    had_room: bool
    owner_deleted_room: bool


@dataclass
class RoomLookupResult:
    room_id: int
    code: str
    title: str
    is_private: bool


@dataclass
class KickPlayerResult:
    snapshot: RoomSnapshot
    kicked_player_tg_user_id: int
    kicked_player_name: str


def _normalize_room_code(room_code: str) -> str:
    return room_code.strip().upper()


def _validate_room_name(title: str) -> str:
    value = title.strip()
    if len(value) < 2 or len(value) > 64:
        raise InvalidRoomConfigError("Название комнаты должно быть от 2 до 64 символов.")
    return value


def _validate_room_password(password: str) -> str:
    value = password.strip()
    if len(value) < 4 or len(value) > 32:
        raise InvalidRoomConfigError("Пароль комнаты должен быть от 4 до 32 символов.")
    return value


def _validate_max_players(max_players: int) -> int:
    if max_players < MIN_ROOM_PLAYERS or max_players > MAX_ROOM_PLAYERS:
        raise InvalidRoomConfigError(
            "Количество игроков должно быть от {} до {}.".format(MIN_ROOM_PLAYERS, MAX_ROOM_PLAYERS)
        )
    return max_players


def _validate_game_mode(game_mode: str) -> str:
    normalized = (game_mode or "").strip().lower()
    if normalized not in (GameMode.CLASSIC.value, GameMode.CUSTOM.value):
        raise InvalidRoomConfigError("Неизвестный формат игры.")
    return normalized


def _player_display_name(user: User) -> str:
    return user.nickname or user.username or user.first_name or "ID:{}".format(user.tg_user_id)


async def _touch_room(session, room_id: int) -> None:
    await session.execute(
        update(Room).where(Room.id == room_id).values(last_activity_at=func.now())
    )


async def _delete_room(session, room_id: int) -> None:
    await session.execute(delete(RoomRoleConfig).where(RoomRoleConfig.room_id == room_id))
    game_session_ids = (
        await session.scalars(
            select(GameSession.id).where(GameSession.room_id == room_id)
        )
    ).all()
    if game_session_ids:
        await session.execute(delete(GameAction).where(GameAction.game_session_id.in_(game_session_ids)))
        await session.execute(delete(GamePlayerState).where(GamePlayerState.game_session_id.in_(game_session_ids)))
        await session.execute(delete(MafiaTurnAction).where(MafiaTurnAction.game_session_id.in_(game_session_ids)))
        await session.execute(delete(GameSession).where(GameSession.id.in_(game_session_ids)))
    await session.execute(delete(Room).where(Room.id == room_id))


async def _find_empty_room_ids(session) -> List[int]:
    empty_room_ids = (
        await session.scalars(
            select(Room.id).where(
                ~select(User.id).where(User.room_id == Room.id).exists()
            )
        )
    ).all()
    return list(empty_room_ids)


async def _get_room_custom_roles_total(session, room_id: int) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(RoomRoleConfig.count), 0)).where(RoomRoleConfig.room_id == room_id)
    )
    return int(total or 0)


async def _generate_room_code(session) -> str:
    for _ in range(30):
        code = "".join(random.choices(ROOM_CODE_ALPHABET, k=ROOM_CODE_LENGTH))
        exists = await session.scalar(
            select(Room.id).where(
                Room.code == code,
                Room.online.is_(True),
            )
        )
        if exists is None:
            return code
    raise RoomControllerError("Не удалось сгенерировать код комнаты.")


async def _get_user_with_lock(session, tg_user_id: int) -> User:
    user = await session.scalar(
        select(User).where(User.tg_user_id == tg_user_id).with_for_update()
    )
    if user is None:
        raise RoomControllerError("Пользователь не найден в базе данных.")
    return user


async def _get_active_room_by_id(session, room_id: int) -> Optional[Room]:
    return await session.scalar(
        select(Room).where(
            Room.id == room_id,
            Room.online.is_(True),
        )
    )


async def _get_active_room_by_code(session, room_code: str) -> Optional[Room]:
    return await session.scalar(
        select(Room).where(
            Room.code == room_code,
            Room.online.is_(True),
        )
    )


async def _build_room_snapshot(session, room: Room) -> RoomSnapshot:
    users = (
        await session.scalars(
            select(User).where(User.room_id == room.id).order_by(User.id.asc())
        )
    ).all()

    players: List[RoomPlayerSnapshot] = []
    for user in users:
        is_owner = user.tg_user_id == room.owner_tg_user_id
        players.append(
            RoomPlayerSnapshot(
                tg_user_id=user.tg_user_id,
                display_name=_player_display_name(user),
                is_ready=True if is_owner else bool(user.room_is_ready),
                is_owner=is_owner,
                role_acknowledged=bool(user.role_acknowledged),
            )
        )

    players.sort(key=lambda item: (not item.is_owner, item.display_name.lower()))
    return RoomSnapshot(
        room_id=room.id,
        code=room.code,
        title=room.title,
        is_private=room.is_private,
        game_mode=room.game_mode or GameMode.CLASSIC.value,
        game_status=room.game_status or "lobby",
        max_players=room.max_players,
        owner_tg_user_id=room.owner_tg_user_id or 0,
        group_link=room.group_link,
        players=players,
    )


async def cleanup_inactive_rooms() -> int:
    async with db() as session:
        inactive_room_ids = (
            await session.scalars(
                select(Room.id).where(
                    Room.online.is_(True),
                    Room.last_activity_at < (func.now() - text("INTERVAL '1 hour'")),
                )
            )
        ).all()

        if not inactive_room_ids:
            empty_room_ids = await _find_empty_room_ids(session)
            if empty_room_ids:
                inactive_game_session_ids = (
                    await session.scalars(select(GameSession.id).where(GameSession.room_id.in_(empty_room_ids)))
                ).all()
                if inactive_game_session_ids:
                    await session.execute(
                        delete(GameAction).where(GameAction.game_session_id.in_(inactive_game_session_ids))
                    )
                    await session.execute(
                        delete(GamePlayerState).where(GamePlayerState.game_session_id.in_(inactive_game_session_ids))
                    )
                    await session.execute(
                        delete(MafiaTurnAction).where(MafiaTurnAction.game_session_id.in_(inactive_game_session_ids))
                    )
                    await session.execute(delete(GameSession).where(GameSession.id.in_(inactive_game_session_ids)))
                await session.execute(delete(RoomRoleConfig).where(RoomRoleConfig.room_id.in_(empty_room_ids)))
                await session.execute(delete(Room).where(Room.id.in_(empty_room_ids)))
                await session.commit()
                return len(empty_room_ids)
            return 0

        await session.execute(
            update(User)
            .where(User.room_id.in_(inactive_room_ids))
            .values(room_id=None, room_is_ready=False, role_id=None, current_role_key=None, role_acknowledged=False)
        )
        inactive_game_session_ids = (
            await session.scalars(select(GameSession.id).where(GameSession.room_id.in_(inactive_room_ids)))
        ).all()
        if inactive_game_session_ids:
            await session.execute(delete(GameAction).where(GameAction.game_session_id.in_(inactive_game_session_ids)))
            await session.execute(delete(GamePlayerState).where(GamePlayerState.game_session_id.in_(inactive_game_session_ids)))
            await session.execute(delete(MafiaTurnAction).where(MafiaTurnAction.game_session_id.in_(inactive_game_session_ids)))
            await session.execute(delete(GameSession).where(GameSession.id.in_(inactive_game_session_ids)))
        await session.execute(delete(RoomRoleConfig).where(RoomRoleConfig.room_id.in_(inactive_room_ids)))
        await session.execute(delete(Room).where(Room.id.in_(inactive_room_ids)))

        empty_room_ids = await _find_empty_room_ids(session)
        if empty_room_ids:
            empty_game_session_ids = (
                await session.scalars(select(GameSession.id).where(GameSession.room_id.in_(empty_room_ids)))
            ).all()
            if empty_game_session_ids:
                await session.execute(delete(GameAction).where(GameAction.game_session_id.in_(empty_game_session_ids)))
                await session.execute(delete(GamePlayerState).where(GamePlayerState.game_session_id.in_(empty_game_session_ids)))
                await session.execute(delete(MafiaTurnAction).where(MafiaTurnAction.game_session_id.in_(empty_game_session_ids)))
                await session.execute(delete(GameSession).where(GameSession.id.in_(empty_game_session_ids)))
            await session.execute(delete(RoomRoleConfig).where(RoomRoleConfig.room_id.in_(empty_room_ids)))
            await session.execute(delete(Room).where(Room.id.in_(empty_room_ids)))

        await session.commit()
        return len(inactive_room_ids)


async def create_room_for_user(
    tg_user_id: int,
    title: str,
    max_players: int,
    password: str,
    group_link: str,
    group_chat_id: Optional[int] = None,
) -> RoomSnapshot:
    await cleanup_inactive_rooms()
    room_title = _validate_room_name(title)
    room_password = _validate_room_password(password)
    room_max_players = _validate_max_players(max_players)
    chat_link = group_link.strip()
    if len(chat_link) < 8:
        raise InvalidRoomConfigError("Ссылка на чат выглядит некорректно.")

    async with db() as session:
        user = await _get_user_with_lock(session, tg_user_id)

        if user.room_id is not None:
            current_room = await _get_active_room_by_id(session, user.room_id)
            if current_room is not None:
                raise UserAlreadyInRoomError(await _build_room_snapshot(session, current_room))
            user.room_id = None
            user.room_is_ready = False
            await session.flush()

        room_code = await _generate_room_code(session)
        room = Room(
            code=room_code,
            title=room_title,
            password=room_password,
            is_private=True,
            game_mode=GameMode.CLASSIC.value,
            max_players=room_max_players,
            group_link=chat_link,
            group_chat_id=group_chat_id,
            owner_tg_user_id=tg_user_id,
            online=True,
        )
        session.add(room)
        await session.flush()

        user.room_id = room.id
        user.room_is_ready = False
        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return snapshot


async def join_room_for_user(tg_user_id: int, room_code: str, password: str) -> RoomSnapshot:
    await cleanup_inactive_rooms()
    normalized_code = _normalize_room_code(room_code)
    if not normalized_code:
        raise RoomNotFoundError("Код комнаты пуст.")

    async with db() as session:
        user = await _get_user_with_lock(session, tg_user_id)
        room = await _get_active_room_by_code(session, normalized_code)
        if room is None:
            raise RoomNotFoundError("Комната не найдена.")
        if room.game_status != "lobby":
            raise RoomControllerError("Игра в этой комнате уже началась.")

        if room.is_private and (room.password or "") != password.strip():
            raise InvalidRoomPasswordError("Неверный пароль комнаты.")

        if user.room_id is not None:
            current_room = await _get_active_room_by_id(session, user.room_id)
            if current_room is not None:
                if current_room.id == room.id:
                    await _touch_room(session, room.id)
                    snapshot = await _build_room_snapshot(session, room)
                    await session.commit()
                    return snapshot
                raise UserAlreadyInRoomError(await _build_room_snapshot(session, current_room))
            user.room_id = None
            user.room_is_ready = False
            await session.flush()

        current_players_count = await session.scalar(
            select(func.count(User.id)).where(User.room_id == room.id)
        )
        if current_players_count is not None and current_players_count >= room.max_players:
            raise RoomIsFullError("Комната уже заполнена.")

        user.room_id = room.id
        user.room_is_ready = False
        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return snapshot


async def get_user_room_snapshot(tg_user_id: int) -> Optional[RoomSnapshot]:
    await cleanup_inactive_rooms()

    async with db() as session:
        user = await session.scalar(select(User).where(User.tg_user_id == tg_user_id))
        if user is None or user.room_id is None:
            return None

        room = await _get_active_room_by_id(session, user.room_id)
        if room is None:
            await session.execute(
                update(User)
                .where(User.tg_user_id == tg_user_id)
                .values(room_id=None, room_is_ready=False)
            )
            await session.commit()
            return None

        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return snapshot


async def get_room_lookup_by_code(room_code: str) -> Optional[RoomLookupResult]:
    await cleanup_inactive_rooms()
    normalized_code = _normalize_room_code(room_code)
    if not normalized_code:
        return None

    async with db() as session:
        room = await _get_active_room_by_code(session, normalized_code)
        if room is None:
            return None

        return RoomLookupResult(
            room_id=room.id,
            code=room.code,
            title=room.title,
            is_private=room.is_private,
        )


async def leave_room_for_user(tg_user_id: int) -> LeaveRoomResult:
    await cleanup_inactive_rooms()

    async with db() as session:
        user = await _get_user_with_lock(session, tg_user_id)
        if user.room_id is None:
            return LeaveRoomResult(had_room=False, owner_deleted_room=False)

        room = await _get_active_room_by_id(session, user.room_id)
        if room is None:
            user.room_id = None
            user.room_is_ready = False
            await session.commit()
            return LeaveRoomResult(had_room=False, owner_deleted_room=False)

        if room.owner_tg_user_id == tg_user_id:
            await session.execute(
                update(User)
                .where(User.room_id == room.id)
                .values(room_id=None, room_is_ready=False, role_id=None, current_role_key=None, role_acknowledged=False)
            )
            await _delete_room(session, room.id)
            await session.commit()
            return LeaveRoomResult(had_room=True, owner_deleted_room=True)

        user.room_id = None
        user.room_is_ready = False
        user.role_id = None
        user.current_role_key = None
        user.role_acknowledged = False
        await session.flush()
        remaining_players_count = await session.scalar(
            select(func.count(User.id)).where(
                User.room_id == room.id,
                User.tg_user_id != tg_user_id,
            )
        )
        if int(remaining_players_count or 0) == 0:
            await _delete_room(session, room.id)
        else:
            await _touch_room(session, room.id)
        await session.commit()
        return LeaveRoomResult(had_room=True, owner_deleted_room=False)


async def toggle_ready_for_user(tg_user_id: int) -> RoomSnapshot:
    await cleanup_inactive_rooms()

    async with db() as session:
        user = await _get_user_with_lock(session, tg_user_id)
        if user.room_id is None:
            raise RoomNotFoundError("Пользователь не состоит в комнате.")

        room = await _get_active_room_by_id(session, user.room_id)
        if room is None:
            user.room_id = None
            user.room_is_ready = False
            await session.commit()
            raise RoomNotFoundError("Комната уже неактивна.")

        if room.owner_tg_user_id == tg_user_id:
            raise RoomControllerError("Владелец комнаты не переключает готовность.")

        user.room_is_ready = not bool(user.room_is_ready)
        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return snapshot


async def _get_owner_room_with_lock(session, owner_tg_user_id: int) -> Room:
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
    return room


async def update_room_name_for_owner(owner_tg_user_id: int, new_title: str) -> RoomSnapshot:
    await cleanup_inactive_rooms()
    validated_title = _validate_room_name(new_title)

    async with db() as session:
        room = await _get_owner_room_with_lock(session, owner_tg_user_id)
        room.title = validated_title
        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return snapshot


async def update_room_password_for_owner(owner_tg_user_id: int, new_password: str) -> RoomSnapshot:
    await cleanup_inactive_rooms()
    validated_password = _validate_room_password(new_password)

    async with db() as session:
        room = await _get_owner_room_with_lock(session, owner_tg_user_id)
        if not room.is_private:
            raise NotRoomOwnerError("Для публичной комнаты пароль не используется.")
        room.password = validated_password
        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return snapshot


async def update_room_game_mode_for_owner(owner_tg_user_id: int, game_mode: str) -> RoomSnapshot:
    await cleanup_inactive_rooms()
    validated_game_mode = _validate_game_mode(game_mode)

    async with db() as session:
        room = await _get_owner_room_with_lock(session, owner_tg_user_id)
        room.game_mode = validated_game_mode
        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return snapshot


async def update_room_max_players_for_owner(owner_tg_user_id: int, delta: int) -> RoomSnapshot:
    await cleanup_inactive_rooms()
    if delta == 0:
        raise InvalidRoomConfigError("Изменение количества игроков должно быть не нулевым.")

    async with db() as session:
        room = await _get_owner_room_with_lock(session, owner_tg_user_id)
        players_count = await session.scalar(
            select(func.count(User.id)).where(User.room_id == room.id)
        )
        players_count = int(players_count or 0)
        next_value = room.max_players + delta
        next_value = max(MIN_ROOM_PLAYERS, min(MAX_ROOM_PLAYERS, next_value))
        configured_roles_total = await _get_room_custom_roles_total(session, room.id)

        if next_value < players_count:
            raise InvalidRoomConfigError(
                "Нельзя поставить лимит меньше текущего числа игроков ({}).".format(players_count)
            )
        if room.game_mode == GameMode.CUSTOM.value and next_value < configured_roles_total:
            raise InvalidRoomConfigError(
                "Нельзя поставить лимит меньше уже настроенного числа ролей ({}).".format(configured_roles_total)
            )

        room.max_players = next_value
        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return snapshot


async def set_room_max_players_for_owner(owner_tg_user_id: int, new_value: int) -> RoomSnapshot:
    await cleanup_inactive_rooms()
    validated_value = _validate_max_players(new_value)

    async with db() as session:
        room = await _get_owner_room_with_lock(session, owner_tg_user_id)
        players_count = await session.scalar(
            select(func.count(User.id)).where(User.room_id == room.id)
        )
        players_count = int(players_count or 0)
        configured_roles_total = await _get_room_custom_roles_total(session, room.id)

        if validated_value < players_count:
            raise InvalidRoomConfigError(
                "Нельзя поставить лимит меньше текущего числа игроков ({}).".format(players_count)
            )
        if room.game_mode == GameMode.CUSTOM.value and validated_value < configured_roles_total:
            raise InvalidRoomConfigError(
                "Нельзя поставить лимит меньше уже настроенного числа ролей ({}).".format(configured_roles_total)
            )

        room.max_players = validated_value
        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return snapshot


async def kick_player_from_room(owner_tg_user_id: int, target_tg_user_id: int) -> KickPlayerResult:
    await cleanup_inactive_rooms()

    async with db() as session:
        room = await _get_owner_room_with_lock(session, owner_tg_user_id)
        if target_tg_user_id == owner_tg_user_id:
            raise InvalidRoomConfigError("Владельца комнаты нельзя кикнуть.")

        target_user = await session.scalar(
            select(User)
            .where(
                User.tg_user_id == target_tg_user_id,
                User.room_id == room.id,
            )
            .with_for_update()
        )
        if target_user is None:
            raise RoomNotFoundError("Игрок не найден в этой комнате.")

        kicked_player_name = _player_display_name(target_user)
        target_user.room_id = None
        target_user.room_is_ready = False
        await _touch_room(session, room.id)
        snapshot = await _build_room_snapshot(session, room)
        await session.commit()
        return KickPlayerResult(
            snapshot=snapshot,
            kicked_player_tg_user_id=target_tg_user_id,
            kicked_player_name=kicked_player_name,
        )

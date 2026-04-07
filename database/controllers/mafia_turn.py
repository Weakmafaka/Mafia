import random
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, update

from database.database import db
from database.models.game_session import GameSession
from database.models.mafia_turn_action import MafiaTurnAction
from database.models.room import Room
from database.models.user import User

from .room import RoomControllerError, RoomNotFoundError


@dataclass
class MafiaTurnMemberSnapshot:
    tg_user_id: int
    display_name: str
    is_viewer: bool
    selected_target_tg_user_id: Optional[int]
    selected_target_name: Optional[str]
    selected_skip: bool
    visit_target_tg_user_id: Optional[int]
    visit_target_name: Optional[str]
    visit_message_sent: bool
    is_ready: bool


@dataclass
class MafiaTurnTargetSnapshot:
    tg_user_id: int
    display_name: str
    current_role_key: str


@dataclass
class MafiaTurnSnapshot:
    game_session_id: int
    room_id: int
    room_title: str
    room_code: str
    group_link: Optional[str]
    group_chat_id: Optional[int]
    group_message_id: Optional[int]
    night_number: int
    deadline_at: Optional[datetime]
    is_resolved: bool
    members: List[MafiaTurnMemberSnapshot]
    kill_targets: List[MafiaTurnTargetSnapshot]
    visit_targets: List[MafiaTurnTargetSnapshot]

    @property
    def single_mafia(self) -> bool:
        return len(self.members) == 1

    @property
    def all_ready(self) -> bool:
        return bool(self.members) and all(member.is_ready for member in self.members)


@dataclass
class MafiaTurnFinalizeResult:
    snapshot: MafiaTurnSnapshot
    outcome_type: str
    target_tg_user_id: Optional[int]
    target_name: Optional[str]
    source: str


@dataclass
class MafiaVisitMessageResult:
    snapshot: MafiaTurnSnapshot
    target_tg_user_id: int
    target_name: str
    message_text: str


@dataclass
class MafiaTeamMessageResult:
    snapshot: MafiaTurnSnapshot
    sender_name: str
    recipient_ids: List[int]
    recipient_names: List[str]
    message_text: str


def _display_name(user: User) -> str:
    return user.nickname or user.username or user.first_name or "ID:{}".format(user.tg_user_id)


def _choice_key(action: MafiaTurnAction) -> Optional[Tuple[str, Optional[int]]]:
    if action.selected_skip:
        return ("skip", None)
    if action.selected_target_tg_user_id is not None:
        return ("target", int(action.selected_target_tg_user_id))
    return None


def _resolve_leading_choice(actions: List[MafiaTurnAction]) -> Optional[Tuple[str, Optional[int]]]:
    counts: Dict[Tuple[str, Optional[int]], int] = {}
    for action in actions:
        choice_key = _choice_key(action)
        if choice_key is None:
            continue
        counts[choice_key] = counts.get(choice_key, 0) + 1

    if not counts:
        return None

    max_votes = max(counts.values())
    leaders = [choice for choice, votes in counts.items() if votes == max_votes]
    if len(leaders) != 1:
        return None
    return leaders[0]


def _choice_label(choice_key: Optional[Tuple[str, Optional[int]]], names_by_id: Dict[int, str]) -> str:
    if choice_key is None:
        return "не выбрал"
    action_type, target_tg_user_id = choice_key
    if action_type == "skip":
        return "пропуск"
    if target_tg_user_id is None:
        return "не выбрал"
    return names_by_id.get(target_tg_user_id, "неизвестная цель")


async def _get_room_users(session, room_id: int, with_lock: bool = False) -> List[User]:
    query = select(User).where(User.room_id == room_id).order_by(User.id.asc())
    if with_lock:
        query = query.with_for_update()
    users = (await session.scalars(query)).all()
    return list(users)


async def _get_mafia_actions(session, game_session_id: int, with_lock: bool = False) -> List[MafiaTurnAction]:
    query = select(MafiaTurnAction).where(MafiaTurnAction.game_session_id == game_session_id)
    if with_lock:
        query = query.with_for_update()
    actions = (await session.scalars(query)).all()
    return list(actions)


async def _build_mafia_turn_snapshot(
    session,
    room: Room,
    game_session: GameSession,
    viewer_tg_user_id: Optional[int] = None,
) -> MafiaTurnSnapshot:
    room_users = await _get_room_users(session, room.id)
    actions = await _get_mafia_actions(session, game_session.id)
    users_by_id = {int(user.tg_user_id): user for user in room_users}
    actions_by_actor = {int(action.actor_tg_user_id): action for action in actions}

    members: List[MafiaTurnMemberSnapshot] = []
    for actor_tg_user_id in sorted(actions_by_actor.keys(), key=lambda item: _display_name(users_by_id[item]).lower()):
        user = users_by_id[actor_tg_user_id]
        action = actions_by_actor[actor_tg_user_id]
        selected_target_name = None
        visit_target_name = None
        if action.selected_target_tg_user_id is not None and int(action.selected_target_tg_user_id) in users_by_id:
            selected_target_name = _display_name(users_by_id[int(action.selected_target_tg_user_id)])
        if action.visit_target_tg_user_id is not None and int(action.visit_target_tg_user_id) in users_by_id:
            visit_target_name = _display_name(users_by_id[int(action.visit_target_tg_user_id)])

        members.append(
            MafiaTurnMemberSnapshot(
                tg_user_id=actor_tg_user_id,
                display_name=_display_name(user),
                is_viewer=viewer_tg_user_id == actor_tg_user_id,
                selected_target_tg_user_id=int(action.selected_target_tg_user_id)
                if action.selected_target_tg_user_id is not None
                else None,
                selected_target_name=selected_target_name,
                selected_skip=bool(action.selected_skip),
                visit_target_tg_user_id=int(action.visit_target_tg_user_id)
                if action.visit_target_tg_user_id is not None
                else None,
                visit_target_name=visit_target_name,
                visit_message_sent=bool(action.visit_message),
                is_ready=bool(action.is_ready),
            )
        )

    kill_targets: List[MafiaTurnTargetSnapshot] = []
    visit_targets: List[MafiaTurnTargetSnapshot] = []
    for user in room_users:
        if (user.current_role_key or "") != "mafia":
            kill_targets.append(
                MafiaTurnTargetSnapshot(
                    tg_user_id=int(user.tg_user_id),
                    display_name=_display_name(user),
                    current_role_key=user.current_role_key or "",
                )
            )
        visit_targets.append(
            MafiaTurnTargetSnapshot(
                tg_user_id=int(user.tg_user_id),
                display_name=_display_name(user),
                current_role_key=user.current_role_key or "",
            )
        )

    kill_targets.sort(key=lambda item: item.display_name.lower())
    visit_targets.sort(key=lambda item: item.display_name.lower())
    return MafiaTurnSnapshot(
        game_session_id=int(game_session.id),
        room_id=int(room.id),
        room_title=room.title,
        room_code=room.code,
        group_link=room.group_link,
        group_chat_id=int(room.group_chat_id) if room.group_chat_id is not None else None,
        group_message_id=int(game_session.group_message_id) if game_session.group_message_id is not None else None,
        night_number=int(game_session.night_number),
        deadline_at=game_session.deadline_at,
        is_resolved=game_session.stage != "mafia",
        members=members,
        kill_targets=kill_targets,
        visit_targets=visit_targets,
    )


async def get_mafia_turn_snapshot_for_room(room_id: int) -> MafiaTurnSnapshot:
    async with db() as session:
        room = await session.scalar(
            select(Room).where(
                Room.id == room_id,
                Room.online.is_(True),
            )
        )
        if room is None:
            raise RoomNotFoundError("Комната не найдена.")
        game_session = await session.scalar(
            select(GameSession).where(
                GameSession.room_id == room.id,
                GameSession.status == "active",
            )
        )
        if game_session is None:
            raise RoomControllerError("Активная игровая сессия не найдена.")
        return await _build_mafia_turn_snapshot(session, room, game_session)


async def get_mafia_turn_snapshot_for_user(tg_user_id: int) -> MafiaTurnSnapshot:
    async with db() as session:
        user = await session.scalar(select(User).where(User.tg_user_id == tg_user_id))
        if user is None or user.room_id is None:
            raise RoomNotFoundError("Пользователь не состоит в комнате.")
        if (user.current_role_key or "") != "mafia":
            raise RoomControllerError("Этот ход сейчас не для тебя.")
        room = await session.scalar(
            select(Room).where(
                Room.id == user.room_id,
                Room.online.is_(True),
            )
        )
        if room is None:
            raise RoomNotFoundError("Комната недоступна.")
        game_session = await session.scalar(
            select(GameSession).where(
                GameSession.room_id == room.id,
                GameSession.status == "active",
            )
        )
        if game_session is None or game_session.stage not in ("mafia", "mafia_resolved"):
            raise RoomControllerError("Сейчас для тебя нет активного хода мафии.")
        return await _build_mafia_turn_snapshot(session, room, game_session, viewer_tg_user_id=tg_user_id)


async def set_mafia_action_message_id(tg_user_id: int, message_id: int) -> None:
    async with db() as session:
        user = await session.scalar(select(User).where(User.tg_user_id == tg_user_id))
        if user is None or user.room_id is None:
            return
        game_session = await session.scalar(
            select(GameSession).where(
                GameSession.room_id == user.room_id,
                GameSession.status == "active",
            )
        )
        if game_session is None:
            return
        await session.execute(
            update(MafiaTurnAction)
            .where(
                MafiaTurnAction.game_session_id == game_session.id,
                MafiaTurnAction.actor_tg_user_id == tg_user_id,
            )
            .values(action_message_id=message_id)
        )
        await session.commit()


async def get_mafia_action_message_targets(game_session_id: int) -> List[Tuple[int, int]]:
    async with db() as session:
        rows = await session.execute(
            select(MafiaTurnAction.actor_tg_user_id, MafiaTurnAction.action_message_id).where(
                MafiaTurnAction.game_session_id == game_session_id,
                MafiaTurnAction.action_message_id.is_not(None),
            )
        )
        return [(int(actor_tg_user_id), int(message_id)) for actor_tg_user_id, message_id in rows.all()]


async def _load_locked_mafia_context(session, tg_user_id: int):
    user = await session.scalar(select(User).where(User.tg_user_id == tg_user_id).with_for_update())
    if user is None or user.room_id is None:
        raise RoomNotFoundError("Пользователь не состоит в комнате.")
    if (user.current_role_key or "") != "mafia":
        raise RoomControllerError("Этот ход доступен только мафии.")

    room = await session.scalar(
        select(Room)
        .where(
            Room.id == user.room_id,
            Room.online.is_(True),
        )
        .with_for_update()
    )
    if room is None:
        raise RoomNotFoundError("Комната недоступна.")

    game_session = await session.scalar(
        select(GameSession)
        .where(
            GameSession.room_id == room.id,
            GameSession.status == "active",
        )
        .with_for_update()
    )
    if game_session is None or game_session.stage != "mafia":
        raise RoomControllerError("Ход мафии сейчас недоступен.")

    room_users = await _get_room_users(session, room.id, with_lock=True)
    actions = await _get_mafia_actions(session, game_session.id, with_lock=True)
    actor_action = None
    for action in actions:
        if int(action.actor_tg_user_id) == tg_user_id:
            actor_action = action
            break
    if actor_action is None:
        raise RoomControllerError("Для игрока не найдено действие мафии.")

    return user, room, game_session, room_users, actions, actor_action


def _get_random_outcome(room_users: List[User]) -> Tuple[str, Optional[int], Optional[str]]:
    targets = [user for user in room_users if (user.current_role_key or "") != "mafia"]
    pool = [("skip", None, None)]
    for target in targets:
        pool.append(("target", int(target.tg_user_id), _display_name(target)))
    outcome_type, target_tg_user_id, target_name = random.choice(pool)
    return outcome_type, target_tg_user_id, target_name


async def _finalize_mafia_turn_locked(
    session,
    room: Room,
    game_session: GameSession,
    room_users: List[User],
    actions: List[MafiaTurnAction],
    source: str,
    forced_choice: Optional[Tuple[str, Optional[int]]] = None,
) -> MafiaTurnFinalizeResult:
    users_by_id = {int(user.tg_user_id): user for user in room_users}
    choice_key = forced_choice or _resolve_leading_choice(actions)
    if choice_key is None:
        outcome_type, target_tg_user_id, target_name = _get_random_outcome(room_users)
    else:
        outcome_type, target_tg_user_id = choice_key
        target_name = _display_name(users_by_id[target_tg_user_id]) if target_tg_user_id in users_by_id else None

    game_session.stage = "mafia_resolved"
    game_session.deadline_at = None
    for action in actions:
        action.is_ready = True

    await session.flush()
    snapshot = await _build_mafia_turn_snapshot(session, room, game_session)
    return MafiaTurnFinalizeResult(
        snapshot=snapshot,
        outcome_type=outcome_type,
        target_tg_user_id=target_tg_user_id,
        target_name=target_name,
        source=source,
    )


async def set_mafia_vote_target(tg_user_id: int, target_tg_user_id: int) -> MafiaTurnSnapshot:
    async with db() as session:
        user, room, game_session, room_users, actions, actor_action = await _load_locked_mafia_context(session, tg_user_id)
        if bool(actor_action.is_ready):
            raise RoomControllerError("Сначала отзови готовность, чтобы изменить выбор.")

        target_user = None
        for candidate in room_users:
            if int(candidate.tg_user_id) == target_tg_user_id:
                target_user = candidate
                break
        if target_user is None:
            raise RoomControllerError("Такого игрока нет в комнате.")
        if (target_user.current_role_key or "") == "mafia":
            raise RoomControllerError("Мафия не может голосовать за свою команду.")

        actor_action.selected_target_tg_user_id = target_tg_user_id
        actor_action.selected_skip = False
        actor_action.is_ready = False
        await session.flush()
        snapshot = await _build_mafia_turn_snapshot(session, room, game_session, viewer_tg_user_id=tg_user_id)
        await session.commit()
        return snapshot


async def set_mafia_skip_choice(tg_user_id: int) -> MafiaTurnSnapshot:
    async with db() as session:
        user, room, game_session, room_users, actions, actor_action = await _load_locked_mafia_context(session, tg_user_id)
        if bool(actor_action.is_ready):
            raise RoomControllerError("Сначала отзови готовность, чтобы изменить выбор.")

        actor_action.selected_target_tg_user_id = None
        actor_action.selected_skip = True
        actor_action.is_ready = False
        await session.flush()
        snapshot = await _build_mafia_turn_snapshot(session, room, game_session, viewer_tg_user_id=tg_user_id)
        await session.commit()
        return snapshot


async def set_mafia_visit_target(tg_user_id: int, target_tg_user_id: int) -> MafiaTurnSnapshot:
    async with db() as session:
        user, room, game_session, room_users, actions, actor_action = await _load_locked_mafia_context(session, tg_user_id)
        if bool(actor_action.is_ready):
            raise RoomControllerError("Сначала отзови готовность, чтобы изменить визит.")

        target_user = None
        for candidate in room_users:
            if int(candidate.tg_user_id) == target_tg_user_id:
                target_user = candidate
                break
        if target_user is None:
            raise RoomControllerError("Такого игрока нет в комнате.")
        if int(target_user.tg_user_id) == tg_user_id:
            raise RoomControllerError("Нельзя зайти к самому себе.")

        actor_action.visit_target_tg_user_id = target_tg_user_id
        actor_action.visit_message = None
        await session.flush()
        snapshot = await _build_mafia_turn_snapshot(session, room, game_session, viewer_tg_user_id=tg_user_id)
        await session.commit()
        return snapshot


async def save_mafia_visit_message(tg_user_id: int, message_text: str) -> MafiaVisitMessageResult:
    normalized_text = (message_text or "").strip()
    if not normalized_text:
        raise RoomControllerError("Сообщение не должно быть пустым.")
    if len(normalized_text) > 300:
        raise RoomControllerError("Сообщение должно быть не длиннее 300 символов.")

    async with db() as session:
        user, room, game_session, room_users, actions, actor_action = await _load_locked_mafia_context(session, tg_user_id)
        if actor_action.visit_target_tg_user_id is None:
            raise RoomControllerError("Сначала выбери, к кому хочешь зайти.")

        target_user = None
        for candidate in room_users:
            if int(candidate.tg_user_id) == int(actor_action.visit_target_tg_user_id):
                target_user = candidate
                break
        if target_user is None:
            raise RoomControllerError("Цель визита больше недоступна.")

        actor_action.visit_message = normalized_text
        await session.flush()
        snapshot = await _build_mafia_turn_snapshot(session, room, game_session, viewer_tg_user_id=tg_user_id)
        await session.commit()
        return MafiaVisitMessageResult(
            snapshot=snapshot,
            target_tg_user_id=int(target_user.tg_user_id),
            target_name=_display_name(target_user),
            message_text=normalized_text,
        )


async def relay_mafia_team_message(tg_user_id: int, message_text: str) -> MafiaTeamMessageResult:
    normalized_text = (message_text or "").strip()
    if not normalized_text:
        raise RoomControllerError("Сообщение не должно быть пустым.")
    if len(normalized_text) > 500:
        raise RoomControllerError("Сообщение должно быть не длиннее 500 символов.")

    async with db() as session:
        user, room, game_session, room_users, actions, actor_action = await _load_locked_mafia_context(session, tg_user_id)
        teammates = [
            teammate
            for teammate in room_users
            if (teammate.current_role_key or "") == "mafia" and int(teammate.tg_user_id) != tg_user_id
        ]
        if not teammates:
            raise RoomControllerError("Сейчас ты единственный мафиози. Секретный чат недоступен.")

        snapshot = await _build_mafia_turn_snapshot(session, room, game_session, viewer_tg_user_id=tg_user_id)
        await session.commit()
        return MafiaTeamMessageResult(
            snapshot=snapshot,
            sender_name=_display_name(user),
            recipient_ids=[int(teammate.tg_user_id) for teammate in teammates],
            recipient_names=[_display_name(teammate) for teammate in teammates],
            message_text=normalized_text,
        )


async def toggle_mafia_ready(tg_user_id: int) -> Tuple[MafiaTurnSnapshot, Optional[MafiaTurnFinalizeResult], bool]:
    async with db() as session:
        user, room, game_session, room_users, actions, actor_action = await _load_locked_mafia_context(session, tg_user_id)
        if bool(actor_action.is_ready):
            actor_action.is_ready = False
            await session.flush()
            snapshot = await _build_mafia_turn_snapshot(session, room, game_session, viewer_tg_user_id=tg_user_id)
            await session.commit()
            return snapshot, None, False

        if _choice_key(actor_action) is None:
            raise RoomControllerError("Сначала выбери жертву или пропуск.")

        ready_map = {int(action.actor_tg_user_id): bool(action.is_ready) for action in actions}
        ready_map[tg_user_id] = True
        if all(ready_map.values()):
            projected_leader = _resolve_leading_choice(actions)
            if projected_leader is None:
                raise RoomControllerError(
                    "Голоса мафии разделились. Нужно выбрать одного человека или один общий пропуск."
                )

        actor_action.is_ready = True
        finalize_result = None
        if all(bool(action.is_ready) for action in actions):
            finalize_result = await _finalize_mafia_turn_locked(
                session=session,
                room=room,
                game_session=game_session,
                room_users=room_users,
                actions=actions,
                source="players",
            )
            await session.commit()
            return finalize_result.snapshot, finalize_result, True

        await session.flush()
        snapshot = await _build_mafia_turn_snapshot(session, room, game_session, viewer_tg_user_id=tg_user_id)
        await session.commit()
        return snapshot, None, True


async def finalize_mafia_turn_on_timeout(game_session_id: int) -> Optional[MafiaTurnFinalizeResult]:
    async with db() as session:
        game_session = await session.scalar(
            select(GameSession)
            .where(GameSession.id == game_session_id)
            .with_for_update()
        )
        if game_session is None or game_session.stage != "mafia":
            return None

        room = await session.scalar(
            select(Room)
            .where(
                Room.id == game_session.room_id,
                Room.online.is_(True),
            )
            .with_for_update()
        )
        if room is None:
            return None

        room_users = await _get_room_users(session, room.id, with_lock=True)
        actions = await _get_mafia_actions(session, game_session.id, with_lock=True)
        if not actions:
            return None

        source = "timeout_random"
        forced_choice = None
        leader = _resolve_leading_choice(actions)
        if leader is not None:
            source = "timeout_existing_votes"
            forced_choice = leader

        finalize_result = await _finalize_mafia_turn_locked(
            session=session,
            room=room,
            game_session=game_session,
            room_users=room_users,
            actions=actions,
            source=source,
            forced_choice=forced_choice,
        )
        await session.commit()
        return finalize_result

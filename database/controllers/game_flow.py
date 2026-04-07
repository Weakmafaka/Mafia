import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import delete, select, update

from database.database import db
from database.models.game_action import GameAction
from database.models.game_player_state import GamePlayerState
from database.models.game_session import GameSession
from database.models.mafia_turn_action import MafiaTurnAction
from database.models.room import Room
from database.models.user import User
from game.classic_mafia.narrator import build_day_vote_result_message
from game.classic_mafia.narrator import build_first_night_message
from game.classic_mafia.narrator import build_night_result_message
from game.classic_mafia.narrator import build_stage_locked_message
from game.classic_mafia.narrator import build_stage_opening_message
from game.classic_mafia.narrator import build_victory_message
from game.classic_mafia.roles import CLASSIC_ROLE_SPECS_BY_KEY

from .room import RoomControllerError, RoomNotFoundError


NIGHT_STAGE_ORDER = ("lover", "commissar", "doctor", "angel", "mafia", "maniac", "ghost")
DAY_VOTE_STAGE = "day_vote"
NIGHT_STAGE_DURATION_SECONDS = 60
DAY_VOTE_DURATION_SECONDS = 60
CITY_TEAMS = {"city"}


ROLE_STAGE_META = {
    "lover": {
        "title": "Ход любовницы",
        "action_button": "Выбрать цель",
        "skip_text": "Пропустить",
        "allow_skip": True,
        "random_mode": "random_target",
    },
    "commissar": {
        "title": "Ход комиссара",
        "action_button": "Проверить игрока",
        "skip_text": "Пропустить проверку",
        "allow_skip": True,
        "random_mode": "random_target",
    },
    "doctor": {
        "title": "Ход доктора",
        "action_button": "Лечить игрока",
        "skip_text": "Не лечить",
        "allow_skip": True,
        "random_mode": "random_target",
        "can_target_self": True,
    },
    "angel": {
        "title": "Ход ангела",
        "action_button": "Защитить игрока",
        "skip_text": "Не защищать",
        "allow_skip": True,
        "random_mode": "random_target",
    },
    "maniac": {
        "title": "Ход маньяка",
        "action_button": "Убить игрока",
        "skip_text": "Пропустить",
        "allow_skip": True,
        "random_mode": "random_target",
    },
    "ghost": {
        "title": "Ход призрака",
        "action_button": "Напугать игрока",
        "skip_text": "Не пугать",
        "allow_skip": True,
        "random_mode": "random_target",
    },
    DAY_VOTE_STAGE: {
        "title": "Утреннее голосование",
        "action_button": "Голосовать",
        "skip_text": "Никого не изгонять",
        "allow_skip": True,
        "random_mode": "skip",
    },
}


@dataclass
class GamePlayerSnapshot:
    tg_user_id: int
    display_name: str
    original_role_key: str
    original_team: str
    current_role_key: str
    is_alive: bool
    can_vote_today: bool
    ghost_fear_available: bool
    ghost_fear_used: bool


@dataclass
class StageActorSnapshot:
    tg_user_id: int
    display_name: str
    is_ready: bool
    selected_target_tg_user_id: Optional[int]
    selected_target_name: Optional[str]
    selected_skip: bool


@dataclass
class StageTargetSnapshot:
    tg_user_id: int
    display_name: str
    is_alive: bool


@dataclass
class StageSnapshot:
    room_id: int
    room_title: str
    room_code: str
    group_link: Optional[str]
    group_chat_id: Optional[int]
    game_session_id: int
    phase: str
    stage: str
    night_number: int
    deadline_at: Optional[datetime]
    group_message_id: Optional[int]
    actors: List[StageActorSnapshot]
    targets: List[StageTargetSnapshot]

    @property
    def all_ready(self) -> bool:
        return bool(self.actors) and all(actor.is_ready for actor in self.actors)


@dataclass
class NightResolutionResult:
    killed_players: List[Tuple[int, str, str]]
    commissar_result: Optional[Tuple[int, str]]
    fearful_players: List[int]


@dataclass
class VictoryResult:
    winner_team: str
    winner_title: str
    winners: List[int]
    losers: List[int]


@dataclass
class StageAdvanceResult:
    next_stage_snapshot: Optional[StageSnapshot]
    finished: bool
    group_message: Optional[str]
    private_messages: Dict[int, str]
    victory_result: Optional[VictoryResult]


def _display_name(user: User) -> str:
    return user.nickname or user.username or user.first_name or "ID:{}".format(user.tg_user_id)


def _stage_choice_label(actor: StageActorSnapshot) -> str:
    if actor.selected_skip:
        return "пропуск"
    if actor.selected_target_name:
        return actor.selected_target_name
    return "не выбрал"


async def initialize_game_player_states(session, game_session_id: int, users: List[User]) -> None:
    await session.execute(delete(GamePlayerState).where(GamePlayerState.game_session_id == game_session_id))
    for user in users:
        role_key = user.current_role_key or "civilian"
        spec = CLASSIC_ROLE_SPECS_BY_KEY.get(role_key)
        if spec is None:
            raise RoomControllerError("Неизвестная роль '{}' при старте игры.".format(role_key))
        session.add(
            GamePlayerState(
                game_session_id=game_session_id,
                tg_user_id=user.tg_user_id,
                original_role_key=role_key,
                original_team=spec.team.value,
                current_role_key=role_key,
                is_alive=True,
                can_vote_today=True,
                ghost_fear_available=False,
                ghost_fear_used=False,
                death_night=0,
            )
        )
    await session.flush()


async def get_room_game_session(session, room_id: int, with_lock: bool = False) -> Optional[GameSession]:
    query = select(GameSession).where(
        GameSession.room_id == room_id,
        GameSession.status == "active",
    )
    if with_lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def _get_room_and_session_for_user(session, tg_user_id: int, with_lock: bool = False):
    user_query = select(User).where(User.tg_user_id == tg_user_id)
    if with_lock:
        user_query = user_query.with_for_update()
    user = await session.scalar(user_query)
    if user is None or user.room_id is None:
        raise RoomNotFoundError("Пользователь не состоит в активной комнате.")

    room_query = select(Room).where(Room.id == user.room_id, Room.online.is_(True))
    if with_lock:
        room_query = room_query.with_for_update()
    room = await session.scalar(room_query)
    if room is None:
        raise RoomNotFoundError("Комната недоступна.")

    game_session = await get_room_game_session(session, room.id, with_lock=with_lock)
    if game_session is None:
        raise RoomControllerError("Активная партия не найдена.")
    return user, room, game_session


async def _get_users_for_room(session, room_id: int, with_lock: bool = False) -> List[User]:
    query = select(User).where(User.room_id == room_id).order_by(User.id.asc())
    if with_lock:
        query = query.with_for_update()
    return list((await session.scalars(query)).all())


async def _get_player_states(session, game_session_id: int, with_lock: bool = False) -> List[GamePlayerState]:
    query = select(GamePlayerState).where(GamePlayerState.game_session_id == game_session_id)
    if with_lock:
        query = query.with_for_update()
    return list((await session.scalars(query)).all())


async def _get_actions_for_stage(
    session,
    game_session_id: int,
    stage: str,
    with_lock: bool = False,
) -> List[GameAction]:
    query = select(GameAction).where(
        GameAction.game_session_id == game_session_id,
        GameAction.stage == stage,
    )
    if with_lock:
        query = query.with_for_update()
    return list((await session.scalars(query)).all())


async def _ensure_stage_actions(
    session,
    game_session_id: int,
    stage: str,
    actor_tg_user_ids: List[int],
) -> None:
    await session.execute(
        delete(GameAction).where(
            GameAction.game_session_id == game_session_id,
            GameAction.stage == stage,
        )
    )
    for actor_tg_user_id in actor_tg_user_ids:
        session.add(
            GameAction(
                game_session_id=game_session_id,
                stage=stage,
                actor_tg_user_id=actor_tg_user_id,
                target_tg_user_id=None,
                selected_skip=False,
                payload_text=None,
                is_ready=False,
                message_id=None,
            )
        )
    await session.flush()


def _next_night_stage(states: List[GamePlayerState]) -> Optional[str]:
    by_role = {}
    for state in states:
        by_role.setdefault(state.original_role_key, []).append(state)

    for stage in NIGHT_STAGE_ORDER:
        if stage == "ghost":
            if any((not state.is_alive) and state.ghost_fear_available and not state.ghost_fear_used for state in states):
                return stage
            continue

        eligible = []
        for state in by_role.get(stage, []):
            if state.is_alive:
                eligible.append(state)
        if eligible:
            return stage
    return None


def _stage_actor_ids(stage: str, states: List[GamePlayerState]) -> List[int]:
    actor_ids: List[int] = []
    for state in states:
        if stage == DAY_VOTE_STAGE:
            if state.is_alive and state.can_vote_today:
                actor_ids.append(int(state.tg_user_id))
            continue
        if stage == "ghost":
            if (not state.is_alive) and state.ghost_fear_available and not state.ghost_fear_used:
                actor_ids.append(int(state.tg_user_id))
            continue
        if state.original_role_key == stage and state.is_alive:
            actor_ids.append(int(state.tg_user_id))
    return actor_ids


def _stage_target_ids(stage: str, states: List[GamePlayerState], actor_tg_user_id: Optional[int] = None) -> List[int]:
    targets: List[int] = []
    actor_state = None
    if actor_tg_user_id is not None:
        for state in states:
            if int(state.tg_user_id) == actor_tg_user_id:
                actor_state = state
                break

    for state in states:
        if stage == "ghost":
            if state.is_alive:
                targets.append(int(state.tg_user_id))
            continue
        if stage == DAY_VOTE_STAGE:
            if state.is_alive:
                targets.append(int(state.tg_user_id))
            continue
        if not state.is_alive:
            continue
        if stage == "doctor":
            targets.append(int(state.tg_user_id))
            continue
        if stage == "angel":
            if actor_state is None or int(state.tg_user_id) != int(actor_state.tg_user_id):
                targets.append(int(state.tg_user_id))
            continue
        if actor_state is not None and int(state.tg_user_id) == int(actor_state.tg_user_id):
            continue
        targets.append(int(state.tg_user_id))
    return targets


async def _set_stage_locked(
    session,
    room: Room,
    game_session: GameSession,
    stage: str,
    states: List[GamePlayerState],
    phase: str,
) -> Optional[StageSnapshot]:
    actor_ids = _stage_actor_ids(stage, states)
    if not actor_ids:
        return None

    if stage == "mafia":
        game_session.phase = phase
        game_session.stage = "mafia"
        game_session.deadline_at = datetime.now(timezone.utc) + timedelta(seconds=NIGHT_STAGE_DURATION_SECONDS)
        game_session.group_message_id = None
        await session.execute(delete(MafiaTurnAction).where(MafiaTurnAction.game_session_id == game_session.id))
        for actor_id in actor_ids:
            session.add(
                MafiaTurnAction(
                    game_session_id=game_session.id,
                    actor_tg_user_id=actor_id,
                    selected_target_tg_user_id=None,
                    selected_skip=False,
                    visit_target_tg_user_id=None,
                    visit_message=None,
                    is_ready=False,
                    action_message_id=None,
                )
            )
        await session.execute(
            delete(GameAction).where(GameAction.game_session_id == game_session.id)
        )
        await session.flush()
        return StageSnapshot(
            room_id=int(room.id),
            room_title=room.title,
            room_code=room.code,
            group_link=room.group_link,
            group_chat_id=int(room.group_chat_id) if room.group_chat_id is not None else None,
            game_session_id=int(game_session.id),
            phase=phase,
            stage="mafia",
            night_number=int(game_session.night_number),
            deadline_at=game_session.deadline_at,
            group_message_id=None,
            actors=[],
            targets=[],
        )

    await session.execute(delete(MafiaTurnAction).where(MafiaTurnAction.game_session_id == game_session.id))
    await _ensure_stage_actions(session, game_session.id, stage, actor_ids)
    game_session.phase = phase
    game_session.stage = stage
    game_session.group_message_id = None
    if stage == DAY_VOTE_STAGE:
        game_session.deadline_at = None
    else:
        game_session.deadline_at = datetime.now(timezone.utc) + timedelta(seconds=NIGHT_STAGE_DURATION_SECONDS)
    await session.flush()
    return await _build_stage_snapshot(session, room, game_session, stage)


async def _build_stage_snapshot(
    session,
    room: Room,
    game_session: GameSession,
    stage: Optional[str] = None,
) -> StageSnapshot:
    current_stage = stage or game_session.stage
    users = await _get_users_for_room(session, room.id)
    states = await _get_player_states(session, game_session.id)
    actions = await _get_actions_for_stage(session, game_session.id, current_stage)
    users_by_id = {int(user.tg_user_id): user for user in users}
    actions_by_actor = {int(action.actor_tg_user_id): action for action in actions}

    actors: List[StageActorSnapshot] = []
    for actor_id in _stage_actor_ids(current_stage, states):
        user = users_by_id.get(actor_id)
        if user is None:
            continue
        action = actions_by_actor.get(actor_id)
        selected_target_name = None
        if action and action.target_tg_user_id is not None and int(action.target_tg_user_id) in users_by_id:
            selected_target_name = _display_name(users_by_id[int(action.target_tg_user_id)])
        actors.append(
            StageActorSnapshot(
                tg_user_id=actor_id,
                display_name=_display_name(user),
                is_ready=bool(action.is_ready) if action else False,
                selected_target_tg_user_id=int(action.target_tg_user_id) if action and action.target_tg_user_id is not None else None,
                selected_target_name=selected_target_name,
                selected_skip=bool(action.selected_skip) if action else False,
            )
        )

    targets: List[StageTargetSnapshot] = []
    for state in states:
        user = users_by_id.get(int(state.tg_user_id))
        if user is None:
            continue
        if current_stage in NIGHT_STAGE_ORDER or current_stage == DAY_VOTE_STAGE:
            targets.append(
                StageTargetSnapshot(
                    tg_user_id=int(state.tg_user_id),
                    display_name=_display_name(user),
                    is_alive=bool(state.is_alive),
                )
            )
    targets.sort(key=lambda item: item.display_name.lower())
    actors.sort(key=lambda item: item.display_name.lower())
    return StageSnapshot(
        room_id=int(room.id),
        room_title=room.title,
        room_code=room.code,
        group_link=room.group_link,
        group_chat_id=int(room.group_chat_id) if room.group_chat_id is not None else None,
        game_session_id=int(game_session.id),
        phase=game_session.phase,
        stage=current_stage,
        night_number=int(game_session.night_number),
        deadline_at=game_session.deadline_at,
        group_message_id=int(game_session.group_message_id) if game_session.group_message_id is not None else None,
        actors=actors,
        targets=targets,
    )


def _check_victory(states: List[GamePlayerState]) -> Optional[VictoryResult]:
    alive_states = [state for state in states if state.is_alive]
    mafia_alive = [state for state in alive_states if state.original_team == "mafia"]
    city_alive = [state for state in alive_states if state.original_team in CITY_TEAMS]
    maniac_alive = [state for state in alive_states if state.original_team == "solo"]

    if maniac_alive and len(alive_states) == 1:
        winner_id = int(maniac_alive[0].tg_user_id)
        losers = [int(state.tg_user_id) for state in states if int(state.tg_user_id) != winner_id]
        return VictoryResult(
            winner_team="solo",
            winner_title="Маньяк",
            winners=[winner_id],
            losers=losers,
        )

    if not mafia_alive and not maniac_alive:
        winners = [int(state.tg_user_id) for state in states if state.original_team in CITY_TEAMS]
        losers = [int(state.tg_user_id) for state in states if state.original_team not in CITY_TEAMS]
        return VictoryResult(
            winner_team="city",
            winner_title="Город",
            winners=winners,
            losers=losers,
        )

    other_alive = len(alive_states) - len(mafia_alive)
    if len(mafia_alive) >= other_alive and not maniac_alive:
        winners = [int(state.tg_user_id) for state in states if state.original_team == "mafia"]
        losers = [int(state.tg_user_id) for state in states if state.original_team != "mafia"]
        return VictoryResult(
            winner_team="mafia",
            winner_title="Мафия",
            winners=winners,
            losers=losers,
        )

    return None


async def _apply_rating_locked(session, room_id: int, game_session_id: int, victory_result: VictoryResult) -> None:
    users = await _get_users_for_room(session, room_id, with_lock=True)
    states = await _get_player_states(session, game_session_id, with_lock=True)
    state_by_user_id = {int(state.tg_user_id): state for state in states}
    winners = set(victory_result.winners)
    for user in users:
        is_winner = int(user.tg_user_id) in winners
        player_state = state_by_user_id.get(int(user.tg_user_id))
        original_team = player_state.original_team if player_state is not None else "city"
        user.games_played += 1
        if is_winner:
            user.wins += 1
            user.rating += 50
        else:
            user.losses += 1
            user.rating -= 50

        if victory_result.winner_team == "mafia" and original_team == "mafia" and is_winner:
            user.mafia_wins += 1
        if victory_result.winner_team == "city" and original_team in CITY_TEAMS and is_winner:
            user.civilian_wins += 1


async def _reset_room_after_game_locked(session, room: Room, game_session: GameSession) -> None:
    await session.execute(
        update(User)
        .where(User.room_id == room.id)
        .values(role_id=None, current_role_key=None, role_acknowledged=False)
    )
    room.game_status = "lobby"
    game_session.group_message_id = None


def _build_victory_message(victory_result: VictoryResult, users_by_id: Dict[int, User]) -> str:
    winners_line = ", ".join(
        _display_name(users_by_id[tg_user_id]) for tg_user_id in victory_result.winners if tg_user_id in users_by_id
    )
    return build_victory_message(victory_result.winner_title, winners_line)


def _blocked_actors_by_lover_and_ghost(
    states: List[GamePlayerState],
    night_actions: Dict[str, Dict[int, Optional[int]]],
) -> Dict[int, str]:
    blocked: Dict[int, str] = {}
    lover_actions = night_actions.get("lover", {})
    for target_tg_user_id in lover_actions.values():
        if target_tg_user_id is not None:
            blocked[int(target_tg_user_id)] = "lover"

    ghost_actions = night_actions.get("ghost", {})
    for target_tg_user_id in ghost_actions.values():
        if target_tg_user_id is not None:
            blocked[int(target_tg_user_id)] = "ghost"
    return blocked


async def _resolve_night_locked(
    session,
    room: Room,
    game_session: GameSession,
) -> NightResolutionResult:
    states = await _get_player_states(session, game_session.id, with_lock=True)
    users = await _get_users_for_room(session, room.id, with_lock=True)
    users_by_id = {int(user.tg_user_id): user for user in users}
    states_by_id = {int(state.tg_user_id): state for state in states}

    stage_actions: Dict[str, Dict[int, Optional[int]]] = {}
    for stage in ("lover", "commissar", "doctor", "angel", "maniac", "ghost"):
        actions = await _get_actions_for_stage(session, game_session.id, stage, with_lock=True)
        stage_actions[stage] = {
            int(action.actor_tg_user_id): (int(action.target_tg_user_id) if action.target_tg_user_id is not None else None)
            for action in actions
            if not action.selected_skip
        }

    mafia_actions = list((await session.scalars(
        select(MafiaTurnAction).where(MafiaTurnAction.game_session_id == game_session.id).with_for_update()
    )).all())
    mafia_target = None
    if game_session.stage in ("mafia_resolved", "commissar", "doctor", "angel", "maniac", "ghost", DAY_VOTE_STAGE):
        from .mafia_turn import _resolve_leading_choice  # local import to avoid circular dependency risk
        leading = _resolve_leading_choice(mafia_actions)
        if leading is not None and leading[0] == "target":
            mafia_target = leading[1]

    blocked = _blocked_actors_by_lover_and_ghost(states, stage_actions)
    doctor_target = None
    for actor_tg_user_id, target_tg_user_id in stage_actions.get("doctor", {}).items():
        if actor_tg_user_id not in blocked:
            doctor_target = target_tg_user_id
    angel_target = None
    for actor_tg_user_id, target_tg_user_id in stage_actions.get("angel", {}).items():
        if actor_tg_user_id not in blocked:
            angel_target = target_tg_user_id

    maniac_target = None
    for actor_tg_user_id, target_tg_user_id in stage_actions.get("maniac", {}).items():
        if actor_tg_user_id not in blocked:
            maniac_target = target_tg_user_id

    commissar_result = None
    commissar_actor_id = None
    commissar_target = None
    for actor_tg_user_id, target_tg_user_id in stage_actions.get("commissar", {}).items():
        if actor_tg_user_id not in blocked:
            commissar_actor_id = actor_tg_user_id
            commissar_target = target_tg_user_id

    fearful_players: List[int] = []
    for actor_tg_user_id, target_tg_user_id in stage_actions.get("ghost", {}).items():
        actor_state = states_by_id.get(actor_tg_user_id)
        if actor_state is None or actor_state.ghost_fear_used or target_tg_user_id is None:
            continue
        actor_state.ghost_fear_used = True
        fearful_players.append(target_tg_user_id)
        target_state = states_by_id.get(target_tg_user_id)
        if target_state is not None:
            target_state.can_vote_today = False

    death_targets = set()
    if mafia_target is not None:
        mafia_blocked = False
        for action in mafia_actions:
            if int(action.actor_tg_user_id) in blocked:
                mafia_blocked = True
                break
        if not mafia_blocked:
            death_targets.add(int(mafia_target))
    if maniac_target is not None:
        death_targets.add(int(maniac_target))

    saved_targets = set()
    if doctor_target is not None:
        saved_targets.add(int(doctor_target))
    if angel_target is not None:
        saved_targets.add(int(angel_target))

    killed_players: List[Tuple[int, str, str]] = []
    for target_tg_user_id in sorted(death_targets):
        if target_tg_user_id in saved_targets:
            continue
        target_state = states_by_id.get(target_tg_user_id)
        target_user = users_by_id.get(target_tg_user_id)
        if target_state is None or target_user is None or not target_state.is_alive:
            continue
        target_state.is_alive = False
        target_state.can_vote_today = False
        target_state.death_night = int(game_session.night_number)
        target_state.current_role_key = "ghost"
        target_state.ghost_fear_available = True
        target_state.ghost_fear_used = False
        killed_players.append((target_tg_user_id, _display_name(target_user), target_state.original_role_key))

    if commissar_actor_id is not None and commissar_target is not None:
        commissar_state = states_by_id.get(commissar_actor_id)
        target_state = states_by_id.get(commissar_target)
        if commissar_state is not None and commissar_state.is_alive and target_state is not None:
            target_spec = CLASSIC_ROLE_SPECS_BY_KEY.get(target_state.original_role_key)
            if target_spec is not None:
                commissar_result = (
                    commissar_actor_id,
                    "Мафия" if target_spec.appears_as_mafia else "Не мафия",
                )

    await session.flush()
    return NightResolutionResult(
        killed_players=killed_players,
        commissar_result=commissar_result,
        fearful_players=fearful_players,
    )


async def build_next_stage_after_role_ack(room_id: int) -> StageAdvanceResult:
    async with db() as session:
        room = await session.scalar(select(Room).where(Room.id == room_id, Room.online.is_(True)).with_for_update())
        if room is None:
            raise RoomNotFoundError("Комната недоступна.")
        game_session = await get_room_game_session(session, room.id, with_lock=True)
        if game_session is None:
            raise RoomControllerError("Игровая сессия не найдена.")
        if game_session.phase != "role_ack" or game_session.stage != "role_ack":
            raise RoomControllerError("Первая игровая стадия уже запущена.")
        states = await _get_player_states(session, game_session.id, with_lock=True)
        next_stage = _next_night_stage(states)
        if next_stage is None:
            game_session.phase = "day"
            game_session.stage = DAY_VOTE_STAGE
            game_session.night_number = max(1, int(game_session.night_number))
            snapshot = await _set_stage_locked(session, room, game_session, DAY_VOTE_STAGE, states, "day")
            await session.commit()
            return StageAdvanceResult(
                snapshot,
                False,
                build_stage_opening_message(DAY_VOTE_STAGE, snapshot.night_number),
                {},
                None,
            )

        if int(game_session.night_number) <= 0:
            game_session.night_number = 1
        snapshot = await _set_stage_locked(session, room, game_session, next_stage, states, "night")
        await session.commit()
        return StageAdvanceResult(
            snapshot,
            False,
            build_first_night_message(next_stage, snapshot.night_number),
            {},
            None,
        )


async def get_stage_snapshot_for_user(tg_user_id: int) -> StageSnapshot:
    async with db() as session:
        _, room, game_session = await _get_room_and_session_for_user(session, tg_user_id, with_lock=False)
        if game_session.stage in ("mafia", "mafia_resolved"):
            raise RoomControllerError("Для текущего этапа используется отдельный интерфейс мафии.")
        if game_session.stage == "finished":
            raise RoomControllerError("Игра уже завершена.")
        snapshot = await _build_stage_snapshot(session, room, game_session)
        if tg_user_id not in {actor.tg_user_id for actor in snapshot.actors}:
            raise RoomControllerError("Этот ход сейчас не для тебя.")
        return snapshot


async def set_stage_action_message_id(tg_user_id: int, message_id: int) -> None:
    async with db() as session:
        _, _, game_session = await _get_room_and_session_for_user(session, tg_user_id, with_lock=False)
        if game_session.stage in ("mafia", "mafia_resolved", "finished"):
            return
        await session.execute(
            update(GameAction)
            .where(
                GameAction.game_session_id == game_session.id,
                GameAction.stage == game_session.stage,
                GameAction.actor_tg_user_id == tg_user_id,
            )
            .values(message_id=message_id)
        )
        await session.commit()


async def set_stage_group_message_id(game_session_id: int, message_id: int) -> None:
    async with db() as session:
        await session.execute(
            update(GameSession)
            .where(GameSession.id == game_session_id)
            .values(group_message_id=message_id)
        )
        await session.commit()


async def get_stage_action_message_targets(game_session_id: int, stage: str) -> List[Tuple[int, int]]:
    async with db() as session:
        rows = await session.execute(
            select(GameAction.actor_tg_user_id, GameAction.message_id).where(
                GameAction.game_session_id == game_session_id,
                GameAction.stage == stage,
                GameAction.message_id.is_not(None),
            )
        )
        return [(int(actor_tg_user_id), int(message_id)) for actor_tg_user_id, message_id in rows.all()]


async def set_generic_stage_target(tg_user_id: int, target_tg_user_id: int) -> StageSnapshot:
    async with db() as session:
        user, room, game_session = await _get_room_and_session_for_user(session, tg_user_id, with_lock=True)
        stage = game_session.stage
        if stage in ("mafia", "mafia_resolved", "finished", "role_ack"):
            raise RoomControllerError("Сейчас этот выбор недоступен.")

        states = await _get_player_states(session, game_session.id, with_lock=True)
        allowed_target_ids = _stage_target_ids(stage, states, actor_tg_user_id=tg_user_id)
        if target_tg_user_id not in allowed_target_ids:
            raise RoomControllerError("Эта цель недоступна для текущего хода.")

        action = await session.scalar(
            select(GameAction)
            .where(
                GameAction.game_session_id == game_session.id,
                GameAction.stage == stage,
                GameAction.actor_tg_user_id == tg_user_id,
            )
            .with_for_update()
        )
        if action is None:
            raise RoomControllerError("Для игрока не найдено активное действие.")
        if action.is_ready:
            raise RoomControllerError("Сначала отзови готовность, чтобы изменить выбор.")

        action.target_tg_user_id = target_tg_user_id
        action.selected_skip = False
        action.is_ready = False
        await session.flush()
        snapshot = await _build_stage_snapshot(session, room, game_session)
        await session.commit()
        return snapshot


async def set_generic_stage_skip(tg_user_id: int) -> StageSnapshot:
    async with db() as session:
        _, room, game_session = await _get_room_and_session_for_user(session, tg_user_id, with_lock=True)
        stage = game_session.stage
        if stage in ("mafia", "mafia_resolved", "finished", "role_ack"):
            raise RoomControllerError("Сейчас пропуск недоступен.")

        action = await session.scalar(
            select(GameAction)
            .where(
                GameAction.game_session_id == game_session.id,
                GameAction.stage == stage,
                GameAction.actor_tg_user_id == tg_user_id,
            )
            .with_for_update()
        )
        if action is None:
            raise RoomControllerError("Для игрока не найдено активное действие.")
        if action.is_ready:
            raise RoomControllerError("Сначала отзови готовность, чтобы изменить выбор.")

        action.target_tg_user_id = None
        action.selected_skip = True
        action.is_ready = False
        await session.flush()
        snapshot = await _build_stage_snapshot(session, room, game_session)
        await session.commit()
        return snapshot


async def _submit_day_vote_choice(
    tg_user_id: int,
    target_tg_user_id: Optional[int],
    selected_skip: bool,
) -> Tuple[StageSnapshot, Optional[StageAdvanceResult]]:
    async with db() as session:
        _, room, game_session = await _get_room_and_session_for_user(session, tg_user_id, with_lock=True)
        if game_session.stage != DAY_VOTE_STAGE:
            raise RoomControllerError("Сейчас город не голосует.")

        states = await _get_player_states(session, game_session.id, with_lock=True)
        action = await session.scalar(
            select(GameAction)
            .where(
                GameAction.game_session_id == game_session.id,
                GameAction.stage == DAY_VOTE_STAGE,
                GameAction.actor_tg_user_id == tg_user_id,
            )
            .with_for_update()
        )
        if action is None:
            raise RoomControllerError("Сегодня ты не участвуешь в голосовании.")

        if selected_skip:
            action.target_tg_user_id = None
            action.selected_skip = True
        else:
            allowed_target_ids = _stage_target_ids(DAY_VOTE_STAGE, states, actor_tg_user_id=tg_user_id)
            if target_tg_user_id not in allowed_target_ids:
                raise RoomControllerError("Этого игрока сейчас нельзя выбрать.")
            action.target_tg_user_id = target_tg_user_id
            action.selected_skip = False

        action.is_ready = True
        await session.flush()
        actions = await _get_actions_for_stage(session, game_session.id, DAY_VOTE_STAGE, with_lock=True)
        if all(item.is_ready for item in actions):
            advance_result = await _advance_from_current_stage_locked(session, room, game_session)
            await session.commit()
            current_snapshot = advance_result.next_stage_snapshot
            if current_snapshot is None:
                current_snapshot = StageSnapshot(
                    room_id=int(room.id),
                    room_title=room.title,
                    room_code=room.code,
                    group_link=room.group_link,
                    group_chat_id=int(room.group_chat_id) if room.group_chat_id is not None else None,
                    game_session_id=int(game_session.id),
                    phase="finished",
                    stage="finished",
                    night_number=int(game_session.night_number),
                    deadline_at=None,
                    group_message_id=None,
                    actors=[],
                    targets=[],
                )
            return current_snapshot, advance_result

        snapshot = await _build_stage_snapshot(session, room, game_session)
        await session.commit()
        return snapshot, None


async def submit_day_vote_target(
    tg_user_id: int,
    target_tg_user_id: int,
) -> Tuple[StageSnapshot, Optional[StageAdvanceResult]]:
    return await _submit_day_vote_choice(
        tg_user_id=tg_user_id,
        target_tg_user_id=target_tg_user_id,
        selected_skip=False,
    )


async def submit_day_vote_skip(tg_user_id: int) -> Tuple[StageSnapshot, Optional[StageAdvanceResult]]:
    return await _submit_day_vote_choice(
        tg_user_id=tg_user_id,
        target_tg_user_id=None,
        selected_skip=True,
    )


def _resolve_day_vote_choice(actions: List[GameAction]) -> Tuple[Optional[int], bool, bool]:
    counts: Dict[Tuple[str, Optional[int]], int] = {}
    for action in actions:
        key = ("skip", None) if action.selected_skip else ("target", int(action.target_tg_user_id) if action.target_tg_user_id is not None else None)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None, True, False
    max_votes = max(counts.values())
    leaders = [key for key, votes in counts.items() if votes == max_votes]
    if len(leaders) != 1:
        return None, False, True
    leader = leaders[0]
    if leader[0] == "skip":
        return None, True, False
    return leader[1], False, False


async def _advance_from_current_stage_locked(session, room: Room, game_session: GameSession) -> StageAdvanceResult:
    states = await _get_player_states(session, game_session.id, with_lock=True)
    users = await _get_users_for_room(session, room.id, with_lock=True)
    users_by_id = {int(user.tg_user_id): user for user in users}

    if game_session.stage == "mafia_resolved":
        next_stage = None
        for candidate in ("maniac", "ghost"):
            if candidate == "ghost":
                if any((not state.is_alive) and state.ghost_fear_available and not state.ghost_fear_used for state in states):
                    next_stage = candidate
                    break
            elif any(state.is_alive and state.original_role_key == candidate for state in states):
                next_stage = candidate
                break
        if next_stage is not None:
            snapshot = await _set_stage_locked(session, room, game_session, next_stage, states, "night")
            return StageAdvanceResult(
                snapshot,
                False,
                "{}\n\n{}".format(
                    build_stage_locked_message("mafia"),
                    build_stage_opening_message(next_stage, snapshot.night_number, previous_stage="mafia"),
                ),
                {},
                None,
            )

        night_result = await _resolve_night_locked(session, room, game_session)
        victory = _check_victory(states)
        private_messages: Dict[int, str] = {}
        if night_result.commissar_result is not None:
            private_messages[night_result.commissar_result[0]] = "Результат проверки: {}.".format(
                night_result.commissar_result[1]
            )

        if victory is not None:
            game_session.status = "finished"
            game_session.phase = "finished"
            game_session.stage = "finished"
            game_session.deadline_at = None
            await _apply_rating_locked(session, room.id, game_session.id, victory)
            await _reset_room_after_game_locked(session, room, game_session)
            return StageAdvanceResult(
                None,
                True,
                "{}\n\n{}".format(
                    build_night_result_message(night_result.killed_players, len(night_result.fearful_players)),
                    _build_victory_message(victory, users_by_id),
                ),
                private_messages,
                victory,
            )

        for state in states:
            if state.is_alive:
                state.can_vote_today = True
        day_snapshot = await _set_stage_locked(session, room, game_session, DAY_VOTE_STAGE, states, "day")
        return StageAdvanceResult(
            day_snapshot,
            False,
            "{}\n\n{}".format(
                build_night_result_message(night_result.killed_players, len(night_result.fearful_players)),
                build_stage_opening_message(DAY_VOTE_STAGE, day_snapshot.night_number),
            ),
            private_messages,
            None,
        )

    if game_session.stage == DAY_VOTE_STAGE:
        actions = await _get_actions_for_stage(session, game_session.id, DAY_VOTE_STAGE, with_lock=True)
        eliminated_tg_user_id, skipped, tie = _resolve_day_vote_choice(actions)
        eliminated_name = None
        if eliminated_tg_user_id is not None:
            for state in states:
                if int(state.tg_user_id) == int(eliminated_tg_user_id) and state.is_alive:
                    state.is_alive = False
                    state.can_vote_today = False
                    state.current_role_key = "ghost"
                    state.ghost_fear_available = True
                    state.ghost_fear_used = False
                    user = users_by_id.get(eliminated_tg_user_id)
                    eliminated_name = _display_name(user) if user is not None else str(eliminated_tg_user_id)
                    break

        victory = _check_victory(states)
        if victory is not None:
            game_session.status = "finished"
            game_session.phase = "finished"
            game_session.stage = "finished"
            game_session.deadline_at = None
            await _apply_rating_locked(session, room.id, game_session.id, victory)
            await _reset_room_after_game_locked(session, room, game_session)
            return StageAdvanceResult(
                None,
                True,
                "{}\n\n{}".format(
                    build_day_vote_result_message(eliminated_name, skipped, tie),
                    _build_victory_message(victory, users_by_id),
                ),
                {},
                victory,
            )

        for state in states:
            state.can_vote_today = True
        game_session.night_number += 1
        next_stage = _next_night_stage(states)
        if next_stage is None:
            game_session.status = "finished"
            game_session.phase = "finished"
            game_session.stage = "finished"
            game_session.deadline_at = None
            victory = VictoryResult("city", "Город", [int(state.tg_user_id) for state in states], [])
            await _apply_rating_locked(session, room.id, game_session.id, victory)
            await _reset_room_after_game_locked(session, room, game_session)
            return StageAdvanceResult(
                None,
                True,
                "{}\n\n{}".format(
                    build_day_vote_result_message(eliminated_name, skipped, tie),
                    _build_victory_message(victory, users_by_id),
                ),
                {},
                victory,
            )

        snapshot = await _set_stage_locked(session, room, game_session, next_stage, states, "night")
        return StageAdvanceResult(
            snapshot,
            False,
            "{}\n\n{}".format(
                build_day_vote_result_message(eliminated_name, skipped, tie),
                build_stage_opening_message(next_stage, snapshot.night_number),
            ),
            {},
            None,
        )

    current_stage_index = NIGHT_STAGE_ORDER.index(game_session.stage)
    next_stage = None
    for candidate in NIGHT_STAGE_ORDER[current_stage_index + 1 :]:
        if candidate == "mafia":
            mafia_states = [state for state in states if state.original_role_key == "mafia" and state.is_alive]
            if mafia_states:
                next_stage = candidate
                break
            continue
        if candidate == "ghost":
            if any((not state.is_alive) and state.ghost_fear_available and not state.ghost_fear_used for state in states):
                next_stage = candidate
                break
            continue
        if any(state.is_alive and state.original_role_key == candidate for state in states):
            next_stage = candidate
            break

    if next_stage is None:
        game_session.stage = "mafia_resolved"
        return await _advance_from_current_stage_locked(session, room, game_session)

    previous_stage = game_session.stage
    snapshot = await _set_stage_locked(session, room, game_session, next_stage, states, "night")
    return StageAdvanceResult(
        snapshot,
        False,
        "{}\n\n{}".format(
            build_stage_locked_message(previous_stage),
            build_stage_opening_message(next_stage, snapshot.night_number, previous_stage=previous_stage),
        ),
        {},
        None,
    )


async def toggle_generic_stage_ready(tg_user_id: int) -> Tuple[StageSnapshot, Optional[StageAdvanceResult], bool]:
    async with db() as session:
        _, room, game_session = await _get_room_and_session_for_user(session, tg_user_id, with_lock=True)
        stage = game_session.stage
        if stage in ("mafia", "mafia_resolved", "finished", "role_ack"):
            raise RoomControllerError("Сейчас подтверждение этого хода недоступно.")

        action = await session.scalar(
            select(GameAction)
            .where(
                GameAction.game_session_id == game_session.id,
                GameAction.stage == stage,
                GameAction.actor_tg_user_id == tg_user_id,
            )
            .with_for_update()
        )
        if action is None:
            raise RoomControllerError("Для игрока не найдено активное действие.")

        if action.is_ready:
            action.is_ready = False
            await session.flush()
            snapshot = await _build_stage_snapshot(session, room, game_session)
            await session.commit()
            return snapshot, None, False

        if not action.selected_skip and action.target_tg_user_id is None:
            raise RoomControllerError("Сначала выбери цель или пропуск.")

        action.is_ready = True
        all_actions = await _get_actions_for_stage(session, game_session.id, stage, with_lock=True)
        became_ready = True
        if all(item.is_ready for item in all_actions):
            advance_result = await _advance_from_current_stage_locked(session, room, game_session)
            await session.commit()
            current_snapshot = advance_result.next_stage_snapshot
            if current_snapshot is None:
                current_snapshot = StageSnapshot(
                    room_id=int(room.id),
                    room_title=room.title,
                    room_code=room.code,
                    group_link=room.group_link,
                    group_chat_id=int(room.group_chat_id) if room.group_chat_id is not None else None,
                    game_session_id=int(game_session.id),
                    phase="finished",
                    stage="finished",
                    night_number=int(game_session.night_number),
                    deadline_at=None,
                    group_message_id=None,
                    actors=[],
                    targets=[],
                )
            return current_snapshot, advance_result, became_ready

        await session.flush()
        snapshot = await _build_stage_snapshot(session, room, game_session)
        await session.commit()
        return snapshot, None, became_ready


async def finalize_generic_stage_on_timeout(game_session_id: int) -> Optional[StageAdvanceResult]:
    async with db() as session:
        game_session = await session.scalar(
            select(GameSession)
            .where(GameSession.id == game_session_id)
            .with_for_update()
        )
        if game_session is None or game_session.stage in ("mafia", "mafia_resolved", "finished", "role_ack"):
            return None

        room = await session.scalar(
            select(Room).where(Room.id == game_session.room_id, Room.online.is_(True)).with_for_update()
        )
        if room is None:
            return None

        actions = await _get_actions_for_stage(session, game_session.id, game_session.stage, with_lock=True)
        states = await _get_player_states(session, game_session.id, with_lock=True)
        for action in actions:
            if action.is_ready:
                continue
            allowed_targets = _stage_target_ids(game_session.stage, states, actor_tg_user_id=int(action.actor_tg_user_id))
            if game_session.stage == DAY_VOTE_STAGE or not allowed_targets:
                action.selected_skip = True
                action.target_tg_user_id = None
            else:
                action.selected_skip = False
                action.target_tg_user_id = random.choice(allowed_targets)
            action.is_ready = True

        advance_result = await _advance_from_current_stage_locked(session, room, game_session)
        await session.commit()
        return advance_result


async def advance_after_mafia_resolution(room_id: int) -> StageAdvanceResult:
    async with db() as session:
        room = await session.scalar(select(Room).where(Room.id == room_id, Room.online.is_(True)).with_for_update())
        if room is None:
            raise RoomNotFoundError("Комната недоступна.")
        game_session = await get_room_game_session(session, room.id, with_lock=True)
        if game_session is None:
            raise RoomControllerError("Игровая сессия не найдена.")
        if game_session.stage != "mafia_resolved":
            raise RoomControllerError("Продолжение после мафии сейчас недоступно.")
        advance_result = await _advance_from_current_stage_locked(session, room, game_session)
        await session.commit()
        return advance_result

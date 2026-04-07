from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import delete, select

from database.models.game_session import GameSession
from database.models.game_action import GameAction
from database.models.mafia_turn_action import MafiaTurnAction
from database.models.user import User


MAFIA_TURN_DURATION_SECONDS = 60


async def ensure_game_session_for_room(session, room_id: int) -> GameSession:
    game_session = await session.scalar(
        select(GameSession).where(GameSession.room_id == room_id).with_for_update()
    )
    if game_session is None:
        game_session = GameSession(
            room_id=room_id,
            status="active",
            phase="role_ack",
            stage="role_ack",
            night_number=0,
            deadline_at=None,
        )
        session.add(game_session)
        await session.flush()
        return game_session

    await session.execute(delete(MafiaTurnAction).where(MafiaTurnAction.game_session_id == game_session.id))
    await session.execute(delete(GameAction).where(GameAction.game_session_id == game_session.id))
    game_session.status = "active"
    game_session.phase = "role_ack"
    game_session.stage = "role_ack"
    game_session.night_number = 0
    game_session.deadline_at = None
    game_session.group_message_id = None
    await session.flush()
    return game_session


async def get_active_session_for_room(session, room_id: int) -> Optional[GameSession]:
    return await session.scalar(
        select(GameSession).where(
            GameSession.room_id == room_id,
            GameSession.status == "active",
        )
    )


async def start_mafia_turn_if_ready(session, room_id: int, room_users: List[User]) -> Optional[GameSession]:
    game_session = await session.scalar(
        select(GameSession).where(GameSession.room_id == room_id).with_for_update()
    )
    if game_session is None:
        return None
    if game_session.phase != "role_ack":
        return None
    if not room_users or any(not bool(user.role_acknowledged) for user in room_users):
        return None

    mafia_users = [user for user in room_users if (user.current_role_key or "") == "mafia"]
    if not mafia_users:
        game_session.phase = "night"
        game_session.stage = "mafia_resolved"
        game_session.deadline_at = None
        await session.execute(delete(MafiaTurnAction).where(MafiaTurnAction.game_session_id == game_session.id))
        await session.flush()
        return None

    game_session.phase = "night"
    game_session.stage = "mafia"
    game_session.night_number = 1 if game_session.night_number <= 0 else game_session.night_number
    game_session.deadline_at = datetime.now(timezone.utc) + timedelta(seconds=MAFIA_TURN_DURATION_SECONDS)
    await session.execute(delete(MafiaTurnAction).where(MafiaTurnAction.game_session_id == game_session.id))
    await session.flush()

    for mafia_user in mafia_users:
        session.add(
            MafiaTurnAction(
                game_session_id=game_session.id,
                actor_tg_user_id=mafia_user.tg_user_id,
                selected_target_tg_user_id=None,
                selected_skip=False,
                visit_target_tg_user_id=None,
                visit_message=None,
                is_ready=False,
                action_message_id=None,
            )
        )

    await session.flush()
    return game_session

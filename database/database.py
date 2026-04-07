import logging
import os

from sqlalchemy import text
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine

from database.models import Base

log = logging.getLogger('database.engine')

engine = create_async_engine(
    URL.create(
        drivername="postgresql+asyncpg",
        username=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "mafia_bot"),
    ),
    future=True,
)

db = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS key VARCHAR(64)"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS team VARCHAR(32)"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS goal TEXT NOT NULL DEFAULT ''"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS night_action_type VARCHAR(32)"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS night_action_priority INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS can_block BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS can_protect BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS can_fear BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS can_seduce BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("UPDATE role SET can_seduce = FALSE WHERE can_seduce IS NULL"))
        await conn.execute(text("ALTER TABLE role ALTER COLUMN can_seduce SET DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS learns_teammates BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS votes_with_team BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS one_time_ability BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(
            text("ALTER TABLE role ADD COLUMN IF NOT EXISTS available_only_after_death BOOLEAN NOT NULL DEFAULT FALSE")
        )
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS can_target_self BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS can_target_others BOOLEAN NOT NULL DEFAULT TRUE"))
        await conn.execute(text("ALTER TABLE role ADD COLUMN IF NOT EXISTS appears_as_mafia BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_role_key ON role (key)"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS title VARCHAR(128) NOT NULL DEFAULT 'Новая комната'"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS password VARCHAR(64)"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS is_private BOOLEAN NOT NULL DEFAULT TRUE"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS game_mode VARCHAR(32) NOT NULL DEFAULT 'classic'"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS game_status VARCHAR(32) NOT NULL DEFAULT 'lobby'"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS max_players INTEGER NOT NULL DEFAULT 6"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS group_link VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS group_chat_id BIGINT"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS owner_tg_user_id BIGINT"))
        await conn.execute(text("ALTER TABLE room ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"))
        await conn.execute(
            text("ALTER TABLE room ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_room_name ON room (name)"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS nickname VARCHAR(64)"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS current_role_key VARCHAR(64)"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role_acknowledged BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS room_is_ready BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS menu_message_id INTEGER"))
        await conn.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE")
        )
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS games_played INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS rating INTEGER NOT NULL DEFAULT 1000"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS wins INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS losses INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS mafia_wins INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS civilian_wins INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS game_session ("
                "id SERIAL PRIMARY KEY, "
                "room_id BIGINT NOT NULL, "
                "status VARCHAR(32) NOT NULL DEFAULT 'active', "
                "phase VARCHAR(32) NOT NULL DEFAULT 'role_ack', "
                "stage VARCHAR(64) NOT NULL DEFAULT 'role_ack', "
                "night_number INTEGER NOT NULL DEFAULT 0, "
                "deadline_at TIMESTAMPTZ NULL, "
                "group_message_id INTEGER NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                ")"
            )
        )
        await conn.execute(text("ALTER TABLE game_session ADD COLUMN IF NOT EXISTS group_message_id INTEGER"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_game_session_room_id ON game_session (room_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_game_session_room_id ON game_session (room_id)"))
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS mafia_turn_action ("
                "id SERIAL PRIMARY KEY, "
                "game_session_id BIGINT NOT NULL, "
                "actor_tg_user_id BIGINT NOT NULL, "
                "selected_target_tg_user_id BIGINT NULL, "
                "selected_skip BOOLEAN NOT NULL DEFAULT FALSE, "
                "visit_target_tg_user_id BIGINT NULL, "
                "visit_message TEXT NULL, "
                "is_ready BOOLEAN NOT NULL DEFAULT FALSE, "
                "action_message_id INTEGER NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                ")"
            )
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_mafia_turn_action_actor "
                "ON mafia_turn_action (game_session_id, actor_tg_user_id)"
            )
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_mafia_turn_action_session ON mafia_turn_action (game_session_id)")
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS game_player_state ("
                "id SERIAL PRIMARY KEY, "
                "game_session_id BIGINT NOT NULL, "
                "tg_user_id BIGINT NOT NULL, "
                "original_role_key VARCHAR(64) NOT NULL, "
                "original_team VARCHAR(32) NOT NULL, "
                "current_role_key VARCHAR(64) NOT NULL, "
                "is_alive BOOLEAN NOT NULL DEFAULT TRUE, "
                "can_vote_today BOOLEAN NOT NULL DEFAULT TRUE, "
                "ghost_fear_available BOOLEAN NOT NULL DEFAULT FALSE, "
                "ghost_fear_used BOOLEAN NOT NULL DEFAULT FALSE, "
                "death_night INTEGER NOT NULL DEFAULT 0, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                ")"
            )
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_game_player_state_actor "
                "ON game_player_state (game_session_id, tg_user_id)"
            )
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_game_player_state_session ON game_player_state (game_session_id)")
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS game_action ("
                "id SERIAL PRIMARY KEY, "
                "game_session_id BIGINT NOT NULL, "
                "stage VARCHAR(64) NOT NULL, "
                "actor_tg_user_id BIGINT NOT NULL, "
                "target_tg_user_id BIGINT NULL, "
                "selected_skip BOOLEAN NOT NULL DEFAULT FALSE, "
                "payload_text TEXT NULL, "
                "is_ready BOOLEAN NOT NULL DEFAULT FALSE, "
                "message_id INTEGER NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                ")"
            )
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_game_action_stage_actor "
                "ON game_action (game_session_id, stage, actor_tg_user_id)"
            )
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_game_action_session ON game_action (game_session_id)"))

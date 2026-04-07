from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from . import Base
from .base import bigint


class GamePlayerState(Base):
    __tablename__ = "game_player_state"
    __table_args__ = (
        UniqueConstraint("game_session_id", "tg_user_id", name="uq_game_player_state_actor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_session_id: Mapped[bigint] = mapped_column(nullable=False, index=True)
    tg_user_id: Mapped[bigint] = mapped_column(nullable=False, index=True)
    original_role_key: Mapped[str] = mapped_column(String(length=64), nullable=False)
    original_team: Mapped[str] = mapped_column(String(length=32), nullable=False)
    current_role_key: Mapped[str] = mapped_column(String(length=64), nullable=False)
    is_alive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_vote_today: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ghost_fear_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ghost_fear_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    death_night: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

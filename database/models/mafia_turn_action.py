from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from . import Base
from .base import bigint


class MafiaTurnAction(Base):
    __tablename__ = "mafia_turn_action"
    __table_args__ = (
        UniqueConstraint("game_session_id", "actor_tg_user_id", name="uq_mafia_turn_action_actor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_session_id: Mapped[bigint] = mapped_column(nullable=False, index=True)
    actor_tg_user_id: Mapped[bigint] = mapped_column(nullable=False, index=True)
    selected_target_tg_user_id: Mapped[Optional[bigint]] = mapped_column(nullable=True)
    selected_skip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visit_target_tg_user_id: Mapped[Optional[bigint]] = mapped_column(nullable=True)
    visit_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

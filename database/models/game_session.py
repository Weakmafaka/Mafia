from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from . import Base
from .base import bigint


class GameSession(Base):
    __tablename__ = "game_session"
    __table_args__ = (UniqueConstraint("room_id", name="uq_game_session_room_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[bigint] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="active")
    phase: Mapped[str] = mapped_column(String(length=32), nullable=False, default="role_ack")
    stage: Mapped[str] = mapped_column(String(length=64), nullable=False, default="role_ack")
    night_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    group_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, VARCHAR, func
from . import Base
from .base import bigint
from sqlalchemy.orm import Mapped, mapped_column


class Room(Base):
    __tablename__ = "room"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column("name", VARCHAR(length=64), nullable=False)
    title: Mapped[str] = mapped_column(VARCHAR(length=128), nullable=False, default="Новая комната")
    password: Mapped[Optional[str]] = mapped_column(VARCHAR(length=64), nullable=True)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    game_mode: Mapped[str] = mapped_column(VARCHAR(length=32), nullable=False, default="classic")
    game_status: Mapped[str] = mapped_column(VARCHAR(length=32), nullable=False, default="lobby")
    max_players: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    group_link: Mapped[Optional[str]] = mapped_column(VARCHAR(length=255), nullable=True)
    group_chat_id: Mapped[Optional[bigint]] = mapped_column(nullable=True)
    owner_tg_user_id: Mapped[Optional[bigint]] = mapped_column(nullable=True)
    online: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

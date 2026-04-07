from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from . import Base
from .base import bigint


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_user_id: Mapped[bigint] = mapped_column(nullable=False, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(length=64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(length=128), nullable=True)
    role_id: Mapped[Optional[bigint]] = mapped_column(nullable=True)
    current_role_key: Mapped[Optional[str]] = mapped_column(String(length=64), nullable=True)
    role_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    room_id: Mapped[Optional[bigint]] = mapped_column(nullable=True)
    room_is_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    menu_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(length=64), nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    games_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mafia_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    civilian_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

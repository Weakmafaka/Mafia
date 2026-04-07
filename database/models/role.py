from typing import Optional

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(length=64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(length=64), nullable=False)
    team: Mapped[str] = mapped_column(String(length=32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    goal: Mapped[str] = mapped_column(Text, nullable=False, default="")
    night_action_type: Mapped[Optional[str]] = mapped_column(String(length=32), nullable=True)
    night_action_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    can_kill: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_check: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_heal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_block: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_protect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_fear: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    learns_teammates: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    votes_with_team: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    one_time_ability: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    available_only_after_death: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_target_self: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_target_others: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    appears_as_mafia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

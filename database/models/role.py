from sqlalchemy import VARCHAR
from . import Base
from .base import bigint


from sqlalchemy.orm import Mapped, mapped_column


class Role(Base):
    __tablename__ = 'role'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(VARCHAR(length=64))
    can_kill: Mapped[bool] = mapped_column()
    can_check: Mapped[bool] = mapped_column()
    can_heal: Mapped[bool] = mapped_column()
    can_seduce: Mapped[bool] = mapped_column()

import asyncio

from sqlalchemy import VARCHAR, select, NUMERIC, Integer
from sqlalchemy.dialects.postgresql import ARRAY

from . import Base
from .base import bigint

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
#3 - польз, комнаты, роли

class User(Base):
    __tablename__ = 'users'

    id: Mapped[bigint] = mapped_column(primary_key=True)
    tg_user_id: Mapped[bigint] = mapped_column(nullable=False)
    role_id: Mapped[bigint] = mapped_column(nullable=False)
    room_id: Mapped[bigint] = mapped_column(nullable=True)




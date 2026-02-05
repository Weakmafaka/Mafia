from sqlalchemy import VARCHAR
from . import Base
from sqlalchemy.orm import Mapped, mapped_column


class Room(Base):
    __tablename__ = 'room'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(VARCHAR(length=64))
    online: Mapped[bool] = mapped_column(default=True)


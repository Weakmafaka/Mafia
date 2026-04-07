from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class RoomRoleConfig(Base):
    __tablename__ = "room_role_config"
    __table_args__ = (
        UniqueConstraint("room_id", "role_key", name="uq_room_role_config_room_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id", ondelete="CASCADE"), nullable=False, index=True)
    role_key: Mapped[str] = mapped_column(String(length=64), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

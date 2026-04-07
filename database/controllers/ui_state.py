from typing import List, Tuple

from sqlalchemy import select, update

from database.database import db
from database.models.user import User


async def set_menu_message_id(tg_user_id: int, message_id: int) -> None:
    async with db() as session:
        await session.execute(
            update(User)
            .where(User.tg_user_id == tg_user_id)
            .values(menu_message_id=message_id)
        )
        await session.commit()


async def get_room_message_targets(room_id: int) -> List[Tuple[int, int]]:
    async with db() as session:
        rows = await session.execute(
            select(User.tg_user_id, User.menu_message_id).where(
                User.room_id == room_id,
                User.menu_message_id.is_not(None),
            )
        )
        return [(int(tg_user_id), int(message_id)) for tg_user_id, message_id in rows.all()]

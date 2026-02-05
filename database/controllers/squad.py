
from sqlalchemy import select

from database.database import db
from database.models.role import Squad


async def new(user_id, name, link):
    async with db.begin() as session:
        session.add(Squad(user_id=user_id, name=name, link=link))
        await session.commit()


async def get(squad_id):
    async with db.begin() as session:
        result = await session.scalar(select(Squad).where(Squad.squad_id == squad_id))
        return result


async def get_all():
    async with db.begin() as session:
        result = await session.scalars(select(Squad))
        return result.all()


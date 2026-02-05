import asyncio
import logging

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine

from database.models import Base

log = logging.getLogger('database.engine')

engine = create_async_engine(
    URL(
        drivername='postgresql+asyncpg',
        username='postgres',
        password='',
        host='localhost',
        port=5432,
        database='game_app_old',
        query={},
    ), future=True,
)

db = async_sessionmaker(engine, expire_on_commit=False)


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

asyncio.run(create_tables())

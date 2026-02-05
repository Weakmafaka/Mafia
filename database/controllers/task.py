from sqlalchemy import select, update, delete

from database.database import db
from database.models.room import Task


async def new(name, link, ref_link, is_bot):
    tasks = await get_all()
    position = len(tasks) + 1

    max_id = 0
    for t in tasks:
        if max_id < t.id:
            max_id = t.id

    async with db.begin() as session:
        session.add(Task(position=position, name=name, link=link, ref_link=ref_link, is_bot=is_bot, id=max_id + 1))
        await session.commit()


async def get(task_id) -> Task:
    async with db.begin() as session:
        result = await session.scalar(select(Task).where(Task.id == task_id))
        return result


async def remove(task_id):
    tasks = await get_all()

    tmp_tasks = []

    for i, t in enumerate(tasks, start=1):
        if task_id == t.id:
            continue

        t.position = i
        tmp_tasks.append(t)

    async with db.begin() as session:
        await session.execute(delete(Task))

        for t in tmp_tasks:
            session.add(Task(id=t.id, name=t.name, link=t.link, ref_link=t.ref_link, is_bot=t.is_bot,
                             checked=t.checked, clicks=t.clicks, position=t.position))

        await session.commit()


async def get_all() -> list[Task]:
    async with db.begin() as session:
        result = await session.scalars(select(Task).order_by(Task.position))
        return result.all()


async def click(task_id):
    async with db.begin() as session:
        await session.execute(update(Task).where(Task.id == task_id).values(clicks=Task.clicks + 1))
        await session.commit()


async def checked(task_id):
    async with db.begin() as session:
        await session.execute(update(Task).where(Task.id == task_id).values(checked=Task.checked + 1))
        await session.commit()


async def update_position(task_position, position):
    tasks = await get_all()

    task = tasks[task_position-1]
    task.position = position

    tasks.pop(task_position-1)
    tasks.insert(position-1, task)

    tmp_tasks = []

    for i, t in enumerate(tasks, start=1):
        t.position = i
        tmp_tasks.append(t)

    async with db.begin() as session:
        await session.execute(delete(Task))

        for t in tmp_tasks:
            session.add(Task(id=t.id, name=t.name, link=t.link, ref_link=t.ref_link, is_bot=t.is_bot,
                             checked=t.checked, clicks=t.clicks, position=t.position))

        await session.commit()

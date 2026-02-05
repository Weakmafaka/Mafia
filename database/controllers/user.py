import asyncio
import urllib
from datetime import datetime, timedelta
from typing import Tuple, Any, Dict

import aiohttp
from sqlalchemy import select, update, ColumnElement, and_, func, text
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.orm.base import _T_co

from cache.models.user import User_redis
from config import ADMINS
from costs import ENERGY_LIMIT
from database.database import db
from database.models.user import User
# from main import send_log

import cache.controllers.user as User_cache
from loader import bot




async def get_panel():
    panel = {}
    panel['all'] = 0
    panel['ref'] = 0
    panel['reflvl1'] = 0
    panel['reflvl2'] = 0
    panel['reflvl3'] = 0
    panel['max_coin'] = 0
    panel['max_cards'] = 0
    panel['online-24'] = 0
    panel['online-15'] = 0
    panel['online_now'] = 0
    now = datetime.now()

    online_24 = now - timedelta(days=1)
    online_15 = now - timedelta(minutes=15)
    online_now = now - timedelta(seconds=10)

    async with db.begin() as session:
        panel['all'] = await session.scalar(select(func.count(User.user_id)))
        panel['ref'] = await session.scalar(text("""SELECT (COUNT(CASE WHEN (ref ~ '^[0-9]+$') THEN 1 END)) FROM users """))
        panel['reflvl1'] = await session.scalar(select(func.sum(User.reflvl1)))
        panel['reflvl2'] = await session.scalar(select(func.sum(User.reflvl2)))
        panel['reflvl3'] = await session.scalar(select(func.sum(User.reflvl3)))
        panel['max_coin'] = await session.scalar(select(func.max(User.coins)))
        panel['online-24'] = await session.scalar(select(func.count(User.user_id)).
                                                  where(User.active_date > online_24))

        panel['new-24'] = await session.scalar(select(func.count(User.user_id)).
                                               where(User.ref_date > online_24))

        panel['online-15'] = await session.scalar(select(func.count(User.user_id)).
                                                  where(User.active_date > online_15))
        panel['online_now'] = await session.scalar(select(func.count(User.user_id)).
                                                   where(User.active_date > online_now))
        return panel


async def new(user_id, ref) -> None:
    async with db.begin() as session:
        session.add(User(user_id=user_id, ref=ref, ref_date=datetime.now()))

        if ref:
            if ref.isdigit():
                if int(ref) == user_id:
                    await session.commit()
                    return

                try:
                    await session.execute(update(User).where(User.user_id == int(ref)).values(reflvl1=User.reflvl1 + 1))

                    ref1 = await get(int(ref))
                    if ref1.ref:
                        if ref1.ref.isdigit():
                            await session.execute(
                                update(User).where(User.user_id == int(ref1.ref)).values(reflvl2=User.reflvl2 + 1))

                            ref2 = await get(int(ref1.ref))
                            if ref2.ref:
                                if ref2.ref.isdigit():
                                    await session.execute(
                                        update(User).where(User.user_id == int(ref2.ref)).values(
                                            reflvl3=User.reflvl3 + 1))

                except Exception as e:
                    await bot.send_message(chat_id=ADMINS[0], text=f'{str(e)} | {user_id} | {ref} ')

        await session.commit()

        try:
            if ref:
                if ref.isdigit():
                    if int(ref) == user_id:
                        return

                    ref = await get(int(ref))
                    ref.reflvl1 += 1
                    await User_cache.update(ref)

                    if ref1.ref:
                        if ref1.ref.isdigit():
                            ref1 = await get(int(ref1.ref))
                            ref1.reflvl2 += 1
                            await User_cache.update(ref1)

                            if ref2.ref:
                                if ref2.ref.isdigit():
                                    ref2 = await get(int(ref2.ref))
                                    ref2.reflvl3 += 1
                                    await User_cache.update(ref2)
        except Exception as e:
            await bot.send_message(chat_id=ADMINS[0], text=f'{str(e)} | {user_id}')


async def update_active(user_id) -> None:
    user = await get(user_id)
    user.active_date = datetime.now()
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).where(User.user_id == user_id).values(active_date=datetime.now()))
        await session.commit()


async def get(user_id, cache=True) -> User_redis | User:

    if cache:
        user = await User_cache.get(user_id)

        if user:
            return user

    async with db.begin() as session:
        user = await session.scalar(select(User).where(User.user_id == user_id))

        if cache:
            await User_cache.new(user)

        return user


async def get_from_db(user_id) -> User:
    async with db.begin() as session:
        result = await session.scalar(select(User).where(User.user_id == user_id))

    return result


async def get_min(user_id) -> dict[str, Any]:
    async with db.begin() as session:
        result = await session.execute(select(User.coins, User.energy).where(User.user_id == user_id))
        result = result.all()[0]
        return {'coins': result[0], 'energy': result[1]}


async def update_wallet(user_id, wallet):
    async with db.begin() as session:
        await session.execute(update(User).where(User.user_id == user_id).values(wallet=wallet))
        await session.commit()


async def click(user_id) -> tuple[InstrumentedAttribute[_T_co] | _T_co, int, int] | tuple[
    ColumnElement[Any] | int | Any, ColumnElement[Any] | int | Any, Any]:

    user = await get(user_id)

    now = datetime.now()

    if user.energy <= 0 and now >= user.tap_guru_end_date:
        return user.coins, 0, 0

    if user.multi_tap_lvl > user.energy:
        coins = user.energy
        energy = 0
    else:
        coins = user.multi_tap_lvl
        energy = user.energy - user.multi_tap_lvl

    now = datetime.now()

    if now <= user.tap_guru_end_date:
        coins = coins * 3
        energy = user.energy

    value = coins

    coins = coins + user.coins
    ref_coins = user.coins

    user.coins = coins
    user.energy = energy
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(coins=coins, energy=energy))

        if (ref_coins // 100) < (coins // 100):

            # await bot.send_message(chat_id=ADMINS[0], text=f'ЕПТА')

            try:
                if user.ref:
                    if user.ref.isdigit():
                        ref1 = await get(int(user.ref))

                        await session.execute(update(User).where(User.user_id == int(user.ref))
                                              .values(coins=User.coins + 15, earn_coins=User.earn_coins + 15))

                        ref1.coins += 15
                        ref1.earn_coins += 15
                        await User_cache.update(ref1)

                        if ref1.ref:
                            if ref1.ref.isdigit():
                                ref2 = await get(int(ref1.ref))

                                await session.execute(
                                    update(User).where(User.user_id == int(ref1.ref))
                                    .values(coins=User.coins + 10, earn_coins=User.earn_coins + 10))

                                ref2.coins += 15
                                ref2.earn_coins += 15
                                await User_cache.update(ref2)

                                if ref2.ref:
                                    if ref2.ref.isdigit():
                                        ref2 = await get(int(ref2.ref))

                                        await session.execute(
                                            update(User).where(User.user_id == int(ref2.ref))
                                            .values(coins=User.coins + 5, earn_coins=User.earn_coins + 5))

                                        ref2.coins += 15
                                        ref2.earn_coins += 15
                                        await User_cache.update(ref2)
            except Exception as e:
                # await bot.send_message(chat_id=ADMINS[0], text=f'{str(e)} | {user_id}')
                pass

        await session.commit()

        return coins, energy, value


async def get_all() -> list[User] | None:
    async with db.begin() as session:
        result = await session.scalars(select(User))
        return result.all()


async def get_coins() -> int:
    async with db.begin() as session:
        result = await session.scalar(select(func.sum(User.coins)))
        return result


async def update_faze(user_id, value):
    async with db.begin() as session:
        await session.execute(update(User).where(User.user_id == user_id).values(faze=value))
        await session.commit()


async def update_coins(user_id, value):
    user = await get(user_id)
    user.coins += value
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).where(User.user_id == user_id).values(coins=User.coins + value))
        await session.commit()


async def update_balance(user_id, value):
    user = await get(user_id)
    user.balance += value
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).where(User.user_id == user_id).values(balance=User.balance + value))

        try:
            if value < 0:
                value = float(-value)

                if user.ref:
                    if user.ref.isdigit():

                        await session.execute(update(User).where(User.user_id == int(user.ref))
                                              .values(balance=User.balance + round(value * 0.15, 2),
                                                      earn_balance=User.earn_balance + round(value * 0.15, 2)))
                        try:
                            ref = await User_cache.get(int(user.ref))
                            ref.balance += round(value * 0.15, 2)
                            ref.earn_balance += round(value * 0.15, 2)
                            await User_cache.update(ref)
                        except:
                            pass

                        ref2 = await get(int(user.ref))

                        if ref2.ref:
                            if ref2.ref.isdigit():

                                await session.execute(
                                    update(User).where(User.user_id == int(ref2.ref))
                                    .values(balance=User.balance + round(value * 0.1, 2),
                                            earn_balance=User.earn_balance + round(value * 0.1, 2)))

                                try:
                                    ref2.balance += round(value * 0.15, 2)
                                    ref2.earn_balance += round(value * 0.15, 2)
                                    await User_cache.update(ref2)

                                except:
                                    pass

                                ref3 = await get(int(user.ref))

                                if ref3.ref:
                                    if ref3.ref.isdigit():
                                        await session.execute(
                                            update(User).where(User.user_id == int(ref3.ref)).values(
                                                balance=User.balance + round(value * 0.05, 2),
                                                earn_balance=User.earn_balance + round(value * 0.05, 2)))

                                        try:
                                            ref3.balance += round(value * 0.15, 2)
                                            ref3.earn_balance += round(value * 0.15, 2)
                                            await User_cache.update(ref3)

                                        except:
                                            pass
        except Exception as e:
            await send_log(e)

        await session.commit()


async def update_stars(user_id, value):
    user = await get(user_id)
    user.stars += value
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).where(User.user_id == user_id).values(stars=User.stars + value))

        try:
            if value < 0:
                value = float(-value)

                if user.ref:
                    if user.ref.isdigit():

                        await session.execute(update(User).where(User.user_id == int(user.ref))
                                              .values(stars=User.stars + round(value * 0.15, 2),
                                                      earn_stars=User.earn_stars + round(value * 0.15, 2)))

                        try:
                            ref = await User_cache.get(int(user.ref))
                            ref.stars += round(value * 0.15, 2)
                            ref.earn_stars += round(value * 0.15, 2)
                            await User_cache.update(ref)
                        except:
                            pass

                        ref2 = await get(int(user.ref))

                        if ref2.ref:
                            if ref2.ref.isdigit():

                                await session.execute(
                                    update(User).where(User.user_id == int(ref2.ref))
                                    .values(stars=User.stars + round(value * 0.1, 2),
                                            earn_stars=User.earn_stars + round(value * 0.1, 2)))

                                try:
                                    ref2.stars += round(value * 0.15, 2)
                                    ref2.earn_stars += round(value * 0.15, 2)
                                    await User_cache.update(ref2)

                                except:
                                    pass

                                ref3 = await get(int(ref2.ref))

                                if ref3.ref:
                                    if ref3.ref.isdigit():
                                        await session.execute(
                                            update(User).where(User.user_id == int(ref3.ref)).values(
                                                stars=User.stars + round(value * 0.05, 2),
                                                earn_stars=User.earn_stars + round(value * 0.05, 2)))

                                        try:
                                            ref3.stars += round(value * 0.15, 2)
                                            ref3.earn_stars += round(value * 0.15, 2)
                                            await User_cache.update(ref3)

                                        except:
                                            pass

        except Exception as e:
            await send_log(e)

        await session.commit()


async def update_multi_tap(user_id):
    user = await get(user_id)
    user.multi_tap_lvl += 1
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).where(User.user_id == user_id).values(multi_tap_lvl=User.multi_tap_lvl + 1))
        await session.commit()


async def update_energy(user_id, value):
    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(energy=value))
        await session.commit()


async def update_energy_limit(user_id, lvl):
    user = await get(user_id)
    user.energy_limit_lvl += 1
    user.energy_limit = ENERGY_LIMIT[lvl][2]

    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(energy_limit=ENERGY_LIMIT[lvl][2], energy_limit_lvl=lvl + 1))
        await session.commit()


async def update_tap_bot(user_id):
    user = await get(user_id)
    user.tap_bot_lvl += 1
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).where(User.user_id == user_id).values(tap_bot_lvl=User.tap_bot_lvl + 1))
        await session.commit()


async def refresh_all():
    now = datetime.now()
    next_date = now + timedelta(hours=3)
    active_date = now - timedelta(hours=10)

    async with db.begin() as session:
        await session.execute(update(User).where(and_(User.energy < User.energy_limit), User.active_date > active_date).
                              values(energy=User.energy + 1))

        await session.execute(update(User).where(and_(and_(User.full_energy < 3,
                                                      User.full_energy_next_reset <= now)),
                                                 User.active_date > active_date).
                              values(full_energy=User.full_energy + 1, full_energy_next_reset=next_date))

        await session.execute(update(User).where(and_(and_(User.tap_guru < 3, User.tap_guru_next_reset <= now))
                                                 , User.active_date > active_date).
                              values(tap_guru=User.tap_guru + 1, tap_guru_next_reset=next_date))

        await session.commit()


async def add_full_energy(user_id):
    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(full_energy=User.full_energy + 1))
        await session.commit()

    await full_energy_next_reset(user_id)


async def add_tap_guru(user_id):
    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(tap_guru=User.tap_guru + 1))
        await session.commit()

    await tap_guru_next_reset(user_id)


async def full_energy_next_reset(user_id):
    next_date = datetime.now() + timedelta(hours=3)

    user = await get(user_id)
    user.full_energy_next_reset = next_date
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(full_energy_next_reset=next_date))
        await session.commit()


async def tap_guru_next_reset(user_id):
    next_date = datetime.now() + timedelta(hours=3)

    user = await get(user_id)
    user.tap_guru_next_reset = next_date
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(tap_guru_next_reset=next_date))
        await session.commit()


async def use_full_energy(user_id):
    user = await get(user_id)
    user.full_energy -= 1
    user.energy = user.energy_limit
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(energy=User.energy_limit, full_energy=User.full_energy - 1))
        await session.commit()


async def use_tap_guru(user_id):
    now = datetime.now()

    user = await get(user_id)
    user.tap_guru -= 1
    user.tap_guru_end_date = now + timedelta(seconds=30)
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(tap_guru=User.tap_guru - 1, tap_guru_end_date=now + timedelta(seconds=30)))
        await session.commit()


async def click_task(user_id, tasks):
    user = await get(user_id)
    user.tasks = tasks
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(tasks=tasks))
        await session.commit()


async def update_cards(user_id, card_id):
    user = await get(user_id)

    cards = []
    if user.cards:
        cards = user.cards

    cards.append(card_id)

    user = await get(user_id)
    user.cards = cards
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).
                              where(User.user_id == user_id).
                              values(cards=cards))
        await session.commit()


async def update_box_next_reset(user_id):
    next_reset = datetime.now() + timedelta(days=1)
    user = await get(user_id)
    user.first_box_next_reset = next_reset
    await User_cache.update(user)

    async with db.begin() as session:
        await session.execute(update(User).where(User.user_id == user_id)
                              .values(first_box_next_reset=next_reset))
        await session.commit()


async def get_eblan():
    async with db.begin() as session:
        result = await session.scalars(select(User))
        return result.all()


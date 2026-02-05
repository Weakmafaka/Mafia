from sqlalchemy import select, update

from database.database import db
from database.models.card import Card


async def new(card):
    card['force'] = list(map(int, card['force'].split(',')))
    card['unforce'] = list(map(int, card['unforce'].split(',')))

    async with db.begin() as session:
        session.add(Card(id=card['id'], name=card['name'], force=card['force'], unforce=card['unforce'],
                         hp=card['hp'], attack=card['attack'], defense=card['defense'],
                         special_attack=card['special_attack'], speed=card['speed'],
                         special_defense=card['special_defense'], cost=card['cost'], ton_cost=card['ton_cost']))
        await session.commit()


async def get(card_id) -> Card:
    async with db.begin() as session:
        result = await session.scalar(select(Card).where(Card.id == card_id))
        return result


async def get_max_lvl(cards: list[int]):
    max = 0
    for card in cards:
        r = await get(card)

        if max < r.lvl:
            max = r.lvl

    return max

# async def get_by_lvl():
#     async with db.begin() as session:
#         cards = await session.scalars(select(Card))
#         cards = cards.all()
#         s = Card
#         for c in cards:
#             lvl = c.hp + c.special_defense+c.defense +c.attack +c.special_attack +c.speed
#             await update_lvl(c.id, lvl)
#
#     print('eblan')
#
#
# async def update_lvl(card_id, lvl):
#     async with db.begin() as session:
#         await session.execute(update(Card).where(Card.id == card_id).values(lvl=lvl))
#         await session.commit()


async def get_all() -> list[Card] | None:
    async with db.begin() as session:
        result = await session.scalars(select(Card))
        return result.all()

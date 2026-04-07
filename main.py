import logging
import asyncio
import os
from dotenv import load_dotenv
from handlers.routers import setup_routers
import sys
from aiogram.types import BotCommand
from core.telegram import bot, dp
from database.controllers.role_catalog import sync_classic_roles
from database.database import init_db
from game.classic_mafia import validate_classic_role_distribution


load_dotenv()

if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Настройка логирования
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console_handler])


async def main():
    validate_classic_role_distribution()
    await init_db()
    await sync_classic_roles()

    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск бота"),
    ])

    # Настройка роутеров
    setup_routers(dp)

    logging.info("Бот Мафия запущен.")

    # Запуск бота
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

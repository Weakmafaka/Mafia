import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
UTILS_ENV_PATH = PROJECT_ROOT / "utils" / ".env"

if ROOT_ENV_PATH.exists():
    load_dotenv(ROOT_ENV_PATH)

if UTILS_ENV_PATH.exists():
    load_dotenv(UTILS_ENV_PATH, override=not ROOT_ENV_PATH.exists())

TOKEN = os.getenv("TOKEN", "").strip()

dp = Dispatcher()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

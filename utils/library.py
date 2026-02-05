import asyncio
import logging
import sys
import random
import os
from datetime import datetime
from pathlib import Path
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import Bot, Dispatcher, Router, types, F, html
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, message, reply_keyboard_markup
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

load_dotenv()

Token = os.getenv('TOKEN')
dp = Dispatcher()
bot = Bot(token=Token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
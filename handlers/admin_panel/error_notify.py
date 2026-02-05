from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, \
    InputMediaPhoto, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.library import bot
from aiogram.exceptions import TelegramBadRequest
import traceback
import logging

admin_chat = -4669367035

async def notify_admins(error_text: str):
    msg = f"⚠️ *Ошибка в боте:*\n```{error_text[-3500:]}```"
    try:
        await bot.send_message(chat_id=admin_chat, text=msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Не удалось отправить ошибку в Telegram: {e}")
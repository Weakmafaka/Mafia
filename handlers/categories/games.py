from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from utils.library import bot
import logging

router = Router()

async def games(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int):
    """Отображает меню с кнопками для запуска игр Mini Apps."""
    
    text = "Выберите игру, в которую хотите сыграть:"
    
    # Создаем кнопки с Mini Apps
    games_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🍉 Fruit Ninja", web_app=WebAppInfo(url="https://poki.com/ru/g/fruit-ninja")),
            InlineKeyboardButton(text="🏃 Subway Surfers", web_app=WebAppInfo(url="https://poki.com/ru/g/subway-surfers"))
        ],
        [
            InlineKeyboardButton(text="🐼 Panda Bubbles", web_app=WebAppInfo(url="https://poki.com/ru/g/panda-bubble-shooter#fullscreen")),
            InlineKeyboardButton(text="🏎️ Polytrack", web_app=WebAppInfo(url="https://poki.com/ru/g/polytrack"))
        ],
        [
             InlineKeyboardButton(text="🎨 Emoji Coloring", web_app=WebAppInfo(url="https://poki.com/ru/g/emoji-coloring")),
             InlineKeyboardButton(text="🚗 Mr Racer", web_app=WebAppInfo(url="https://poki.com/ru/g/mr-racer-car-racing"))
        ],
        [
            InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_main")
        ]
    ])
    
    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id_to_edit,
            text=text,
            reply_markup=games_keyboard
        )
        # Сохраняем ID сообщения, чтобы его можно было удалить/изменить при возврате в главное меню
        await state.update_data(message_to_delete=message_id_to_edit) 
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения в games: {e}")
        # В случае ошибки отправляем новое сообщение
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_id_to_edit)
        except Exception as del_e:
            logging.warning(f"Не удалось удалить старое сообщение в games: {del_e}")
        new_msg = await bot.send_message(user_id, text, reply_markup=games_keyboard)
        await state.update_data(message_to_delete=new_msg.message_id)
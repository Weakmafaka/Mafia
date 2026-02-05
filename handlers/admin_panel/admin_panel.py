from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from utils.library import bot

router = Router()

MAIN_ADMIN_ID = 768903494

@router.callback_query(F.data == 'admin_panel')
async def admin_panel(query: CallbackQuery, state : FSMContext):
    try:
        await bot.delete_message(chat_id=query.message.chat.id,
                                 message_id=query.message.message_id)
    except Exception as ex:
        pass

    from main import db
    is_admin = db.is_admin(query.from_user.id)
    if is_admin:
        menu_buttons = [
            [
                InlineKeyboardButton(text="Категории 💎", callback_data="admin_category")
            ],
            [
                InlineKeyboardButton(text="Статистика 📈", callback_data="admin_stat"),
                InlineKeyboardButton(text="Рассылка 📝", callback_data="admin_notify")
            ]
        ]
        
        # Добавляем кнопку дарения подписки только для главного администратора
        if query.from_user.id == MAIN_ADMIN_ID:
            menu_buttons.insert(2, [
                InlineKeyboardButton(text="Подарить подписку 🎁", callback_data="admin_gift_subscription")
            ])
            
        menu_buttons.append([
            InlineKeyboardButton(text="Вернуться назад ⏪", callback_data="change_age")
        ])
        
        menu = InlineKeyboardMarkup(inline_keyboard=menu_buttons)

        await bot.send_message(chat_id=query.message.chat.id,
                               text=f"Здравствуйте о великий АдМиНиСтРаТоР @{query.from_user.username}",
                               reply_markup=menu)
    else:
        return
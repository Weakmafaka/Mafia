from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from utils.library import bot
from Database.database import db
from handlers.admin_panel.error_notify import notify_admins
from utils.logger import get_logger

logger = get_logger(__name__)

router = Router()

class GiftSubscriptionState(StatesGroup):
    waiting_for_username = State()
    waiting_for_duration = State()

MAIN_ADMIN_ID = 768903494

@router.callback_query(F.data == "admin_gift_subscription")
async def gift_subscription_start(query: CallbackQuery, state: FSMContext):
    """Начало процесса дарения подписки"""
    if query.from_user.id != MAIN_ADMIN_ID:
        logger.warning("unauthorized_gift_attempt", 
            user_id=query.from_user.id,
            username=query.from_user.username
        )
        await query.answer("У вас нет доступа к этой функции", show_alert=True)
        return

    # Удаляем предыдущее сообщение с кнопкой
    try:
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception as e:
        logger.error("message_delete_error",
            user_id=query.from_user.id,
            error=str(e),
            chat_id=query.message.chat.id,
            message_id=query.message.message_id
        )

    menu_buttons = [
        [InlineKeyboardButton(text="Отмена 🚫", callback_data="admin_cancel")]
    ]
    menu = InlineKeyboardMarkup(inline_keyboard=menu_buttons)

    # Отправляем сообщение и сохраняем его ID
    sent_msg = await bot.send_message(
        chat_id=query.from_user.id,
        text="Введите никнейм пользователя (без @), которому хотите подарить подписку:",
        reply_markup=menu
    )

    await state.set_state(GiftSubscriptionState.waiting_for_username)
    await state.update_data(messages_to_delete=[sent_msg.message_id])

@router.message(GiftSubscriptionState.waiting_for_username)
async def process_username(message: Message, state: FSMContext):
    """Обработка введенного никнейма пользователя"""
    if message.from_user.id != MAIN_ADMIN_ID:
        return

    username = message.text.strip().lower()
    if username.startswith('@'):
        username = username[1:]

    try:
        # Проверяем существование пользователя в базе по никнейму
        user = db.get_user_by_username(username)
        if not user:
            logger.warning("gift_recipient_not_found",
                admin_id=message.from_user.id,
                target_username=username
            )
            raise ValueError("Пользователь не найден в базе")
        
        user_id = user['user_id']
        logger.info("gift_recipient_found",
            admin_id=message.from_user.id,
            target_user_id=user_id,
            target_username=username
        )
    except ValueError as e:
        error_msg = await message.answer(
            "❌ Пользователь с таким никнеймом не найден в базе. Попробуйте еще раз:"
        )
        data = await state.get_data()
        messages_to_delete = data.get('messages_to_delete', [])
        messages_to_delete.append(message.message_id)
        messages_to_delete.append(error_msg.message_id)
        await state.update_data(messages_to_delete=messages_to_delete)
        return

    # Сохраняем данные пользователя
    data = await state.get_data()
    messages_to_delete = data.get('messages_to_delete', [])
    messages_to_delete.append(message.message_id)
    
    # Создаем клавиатуру с вариантами длительности
    duration_buttons = [
        [
            InlineKeyboardButton(text="1 месяц", callback_data="gift_duration_30"),
            InlineKeyboardButton(text="3 месяца", callback_data="gift_duration_90")
        ],
        [
            InlineKeyboardButton(text="6 месяцев", callback_data="gift_duration_180"),
            InlineKeyboardButton(text="12 месяцев", callback_data="gift_duration_365")
        ],
        [InlineKeyboardButton(text="Отмена 🚫", callback_data="admin_cancel")]
    ]
    duration_keyboard = InlineKeyboardMarkup(inline_keyboard=duration_buttons)

    # Отправляем сообщение с выбором длительности
    msg = await message.answer(
        f"Выберите длительность подписки для пользователя @{username}:",
        reply_markup=duration_keyboard
    )
    
    messages_to_delete.append(msg.message_id)
    await state.update_data(
        target_user_id=user_id,
        target_username=username,
        messages_to_delete=messages_to_delete
    )
    await state.set_state(GiftSubscriptionState.waiting_for_duration)

@router.callback_query(lambda c: c.data.startswith('gift_duration_'))
async def process_duration(query: CallbackQuery, state: FSMContext):
    """Обработка выбранной длительности подписки"""
    if query.from_user.id != MAIN_ADMIN_ID:
        logger.warning("unauthorized_duration_selection",
            user_id=query.from_user.id,
            username=query.from_user.username
        )
        await query.answer("У вас нет доступа к этой функции", show_alert=True)
        return

    try:
        duration_days = int(query.data.split('_')[2])
        data = await state.get_data()
        user_id = data.get('target_user_id')
        username = data.get('target_username')

        if not user_id:
            logger.error("missing_user_data",
                admin_id=query.from_user.id,
                state_data=data
            )
            raise ValueError("Данные пользователя не найдены")

        # Активируем премиум подписку
        db.set_premium_status(user_id, True, duration_days)
        
        logger.info("gift_subscription_activated",
            admin_id=query.from_user.id,
            target_user_id=user_id,
            target_username=username,
            duration_days=duration_days
        )

        # Уведомляем пользователя о получении подписки
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎁 Поздравляем!\nВам подарили премиум подписку на {duration_days} дней!"
            )
        except Exception as e:
            logger.error("notification_failed",
                admin_id=query.from_user.id,
                target_user_id=user_id,
                target_username=username,
                error=str(e)
            )
            await notify_admins(f"Ошибка при отправке уведомления о подарке пользователю @{username}")

        # Очищаем все сообщения
        messages_to_delete = data.get('messages_to_delete', [])
        for msg_id in messages_to_delete:
            try:
                await bot.delete_message(chat_id=query.message.chat.id, message_id=msg_id)
            except Exception as e:
                logger.warning("message_cleanup_error",
                    message_id=msg_id,
                    chat_id=query.message.chat.id,
                    error=str(e)
                )

        # Отправляем подтверждение
        success_msg = await bot.send_message(
            chat_id=query.from_user.id,
            text=f"✅ Подписка успешно подарена пользователю @{username} на {duration_days} дней!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Вернуться в админ-панель ⏪", callback_data="admin_panel")]
            ])
        )

        await state.clear()

    except Exception as e:
        logger.error("gift_subscription_error",
            admin_id=query.from_user.id,
            error=str(e),
            error_type=type(e).__name__
        )
        await notify_admins(f"Критическая ошибка при дарении подписки: {e}")
        await query.answer("Произошла ошибка. Попробуйте еще раз.", show_alert=True)
        # Возвращаемся в админ-панель
        from handlers.admin_panel.admin_panel import admin_panel
        await admin_panel(query, state) 
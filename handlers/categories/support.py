from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from utils.library import bot
import logging

router = Router()

@router.callback_query(F.data == 'support')
async def send_category(query: CallbackQuery, state: FSMContext):
    await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    # Редактируем текущее сообщение, показывая информацию о поддержке
    data = await state.get_data()

    help_text = (
        "✨ *Привет, дорогой пользователь!* ✨\n\n"
        "Я — Янтарик, твой волшебный помощник в мире детства! 🧚‍♀️\n\n"
        "🎯 *Как мной пользоваться:*\n\n"
        "1️⃣ Выбери возрастную группу своего малыша — это поможет мне подобрать самый классный контент\n\n"
        "2️⃣ В главном меню ты найдешь кнопочки с разделами:\n"
        "   • 🧜 *Мультики* — любимые мультфильмы для деток\n"
        "   • 🎤 *Музыка* — веселые песенки и колыбельные\n"
        "   • 🧙‍♀ *Сказки* — волшебные истории на ночь\n"
        "   • 🎮 *Игры* — веселые игры для детей (от 4-х до 10 лет)\n"
        "   • 🔓 *Полезное* — раздел с материалами для развития\n"
        "   • 🤖 *AI Помощник* — умный волшебник, который понимает текст, картинки и даже голос!\n"
        "         Просто напиши, пришли фото или скажи что-нибудь — и он постарается помочь 😊\n\n"


        "3️⃣ Для возврата в меню используй кнопку *Назад* ⬅️\n\n"

        "🪄 *Полезные команды:*\n"
        "/start — перезапустить бота\n\n"

        "🎁 *Премиум подписка* – дает доступ ко всем разделам и уникальным материалам!\n"
        "🎁 *Подарить подписку* – отправь подписку на месяц близкому человеку!\n\n"
        "По поводу предложений или сотрудничества пишите на почту или в телеграмм:\nyantarikproject@yandex.ru\n@Yantarick\n\n"
        "Я всегда готов дарить радость твоему малышу! ❤️"

    )

    # Кнопка для возврата в главное меню
    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="О нас ℹ️", web_app=WebAppInfo(url="https://fabulous-vacherin-e3110d.netlify.app")),
        InlineKeyboardButton(text="Вернуться в меню 🏠", callback_data="back_to_main")]
    ])

    # Отправляем сообщение с инструкцией
    try:
        await bot.send_message(text=help_text, reply_markup=back_button, parse_mode="Markdown", chat_id=query.from_user.id)
    except Exception as e:
        # Если возникла ошибка с Markdown форматированием, отправляем без форматирования
        logging.error(f"Ошибка при отправке help: {e}")
        await bot.send_message(text=help_text.replace('*', ''), reply_markup=back_button, chat_id=query.from_user.id)

    # Получаем текущие данные
    data = await state.get_data()


@router.callback_query(F.data == 'back_to_main')
async def back_to_main(query: CallbackQuery, state: FSMContext):
    """Обработка нажатия на кнопку "Назад" - возврат в главное меню"""
    # Получаем сохраненный возраст пользователя из БД
    from main import db
    age_group = db.get_user_age(query.from_user.id)
    
    if not age_group:
        # Если возраст не задан, просим выбрать его (редактируем текущее сообщение)
        # Так как command_start ожидает Message, а не CallbackQuery, 
        # передаем основные данные вручную или вызываем функцию запроса возраста
        # Проще всего вызвать change_age, которая покажет кнопки выбора возраста
        from handlers.common import change_age
        await change_age(query, state)
        return
    
    # Показываем главное меню с учетом сохраненного возраста (редактируем текущее сообщение)
    from handlers.common import show_main_menu
    await show_main_menu(query.from_user.id, age_group, state, message_to_edit_id=query.message.message_id) 
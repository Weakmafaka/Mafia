from typing import Union
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import logging

from utils.library import bot


router = Router()


class NotifyState(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    confirmation = State()


async def cleanup_chat(chat_id: int, message_ids: list):
    """Удаление нескольких сообщений в чате"""
    for msg_id in message_ids:
        if msg_id is None:
            continue
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logging.warning(f"Не удалось удалить сообщение {msg_id}: {e}")



@router.callback_query(F.data == "admin_notify")
async def notify_start(query: CallbackQuery, state: FSMContext):
    """Начало процесса создания рассылки"""
    from main import db
    if not db.is_admin(query.from_user.id):
        return

    # Удаляем предыдущее сообщение с кнопкой
    try:
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception as e:
        logging.error(f"Не удалось удалить сообщение: {e}")

    menu_buttons = [
        [InlineKeyboardButton(text="Отмена 🚫", callback_data="admin_cancel")]
    ]
    menu = InlineKeyboardMarkup(inline_keyboard=menu_buttons)

    # Отправляем сообщение и сохраняем его ID
    sent_msg = await bot.send_message(
        chat_id=query.from_user.id,
        text="📝 Напишите текст сообщения для рассылки:",
        reply_markup=menu
    )

    await state.set_state(NotifyState.waiting_for_text)

    # ВНИМАНИЕ: добавляем ID в список для удаления
    await state.update_data(
        main_message_id=sent_msg.message_id,
        messages_to_delete=[
            query.message.message_id,  # старое сообщение с кнопкой
            sent_msg.message_id        # сообщение "Напишите текст..."
        ]
    )



@router.message(NotifyState.waiting_for_text)
async def notify_get_text(message: Message, state: FSMContext):
    """Получение текста для рассылки"""
    data = await state.get_data()
    messages_to_delete = data.get("messages_to_delete", [])

    # Добавляем сообщение пользователя
    messages_to_delete.append(message.message_id)

    # Отправляем подсказку для следующего шага
    menu_buttons = [
        [InlineKeyboardButton(text="Пропустить ➡️", callback_data="skip_media")],
        [InlineKeyboardButton(text="Отмена 🚫", callback_data="admin_cancel")]
    ]
    menu = InlineKeyboardMarkup(inline_keyboard=menu_buttons)

    hint_msg = await bot.send_message(
        chat_id=message.chat.id,
        text="📷 Теперь отправьте медиафайл (фото, видео, документ или аудио) или нажмите 'Пропустить':",
        reply_markup=menu
    )

    # Сохраняем всё
    messages_to_delete.append(hint_msg.message_id)
    await state.update_data(
        text=message.text,
        messages_to_delete=messages_to_delete
    )
    await state.set_state(NotifyState.waiting_for_media)



@router.callback_query(F.data == "skip_media", NotifyState.waiting_for_media)
async def skip_media(query: CallbackQuery, state: FSMContext):
    """Пропуск медиа"""
    try:
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception as e:
        logging.error(f"Не удалось удалить сообщение: {e}")

    data = await state.get_data()
    messages_to_delete = data.get("messages_to_delete", [])
    messages_to_delete.append(query.message.message_id)
    await state.update_data(messages_to_delete=messages_to_delete)

    await show_confirmation(query, state)



@router.message(NotifyState.waiting_for_media)
async def notify_get_media(message: Message, state: FSMContext):
    """Получение медиа для рассылки"""
    data = await state.get_data()
    messages_to_delete = data.get("messages_to_delete", [])

    media = None
    if message.photo:
        media = ("photo", message.photo[-1].file_id)
    elif message.video:
        media = ("video", message.video.file_id)
    elif message.document:
        media = ("document", message.document.file_id)
    elif message.audio:
        media = ("audio", message.audio.file_id)

    if media:
        media_type, media_id = media
        messages_to_delete.append(message.message_id)
        await state.update_data(
            media_type=media_type,
            media_id=media_id,
            messages_to_delete=messages_to_delete
        )
        await show_confirmation(message, state)
    else:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception as e:
            logging.error(f"Не удалось удалить сообщение: {e}")

        error_msg = await message.answer("⚠️ Пожалуйста, отправьте фото, видео, документ или аудио.")
        messages_to_delete.append(error_msg.message_id)
        await state.update_data(messages_to_delete=messages_to_delete)



async def show_confirmation(update: Union[Message, CallbackQuery], state: FSMContext):
    """Показ подтверждения перед рассылкой"""
    data = await state.get_data()
    text = data.get("text", "Без текста")
    media_type = data.get("media_type")
    media_id = data.get("media_id")
    messages_to_delete = data.get("messages_to_delete", [])

    # Удаляем все прошлые сообщения
    await cleanup_chat(update.from_user.id, messages_to_delete)

    # Отправляем предпросмотр
    if media_type:
        if media_type == "photo":
            sent_message = await bot.send_photo(chat_id=update.from_user.id, photo=media_id, caption=text)
        elif media_type == "video":
            sent_message = await bot.send_video(chat_id=update.from_user.id, video=media_id, caption=text)
        elif media_type == "document":
            sent_message = await bot.send_document(chat_id=update.from_user.id, document=media_id, caption=text)
        elif media_type == "audio":
            sent_message = await bot.send_audio(chat_id=update.from_user.id, audio=media_id, caption=text)
        else:
            sent_message = await bot.send_message(chat_id=update.from_user.id, text=text)
        preview_message_id = sent_message.message_id
    else:
        sent_message = await bot.send_message(chat_id=update.from_user.id, text=text)
        preview_message_id = sent_message.message_id

    # Кнопки подтверждения
    menu_buttons = [
        [InlineKeyboardButton(text="Отправить рассылку ✅", callback_data="confirm_send")],
        [InlineKeyboardButton(text="Отмена 🚫", callback_data="admin_cancel")]
    ]
    menu = InlineKeyboardMarkup(inline_keyboard=menu_buttons)

    confirm_msg = await bot.send_message(
        chat_id=update.from_user.id,
        text="🔍 Вот как будет выглядеть ваше сообщение. Подтвердите отправку:",
        reply_markup=menu
    )

    # Обновляем состояние
    await state.set_state(NotifyState.confirmation)
    await state.update_data(
        preview_message_id=preview_message_id,
        confirm_message_id=confirm_msg.message_id,
        messages_to_delete=[]
    )




@router.callback_query(F.data == "confirm_send", NotifyState.confirmation)
async def confirm_send(query: CallbackQuery, state: FSMContext):
    """Подтверждение и отправка рассылки"""
    from main import db
    data = await state.get_data()
    text = data.get("text")
    media_type = data.get("media_type")
    media_id = data.get("media_id")
    preview_message_id = data.get("preview_message_id")
    confirm_message_id = data.get("confirm_message_id")

    # Удаляем сообщения предпросмотра и подтверждения
    await cleanup_chat(query.from_user.id, [preview_message_id, confirm_message_id])

    users = db.get_all_users()
    total_users = len(users)
    success = 0
    failed = 0

    for user in users:
        try:
            if media_type == "photo":
                await bot.send_photo(user['user_id'], media_id, caption=text)
            elif media_type == "video":
                await bot.send_video(user['user_id'], media_id, caption=text)
            elif media_type == "document":
                await bot.send_document(user['user_id'], media_id, caption=text)
            elif media_type == "audio":
                await bot.send_audio(user['user_id'], media_id, caption=text)
            else:
                await bot.send_message(user['user_id'], text)
            success += 1
        except Exception as e:
            logging.error(f"Ошибка при отправке {user['user_id']}: {e}")
            failed += 1

    # Итоговое сообщение
    menu_buttons = [
        [InlineKeyboardButton(text="Вернуться в админ-панель ⏪", callback_data="admin_panel")]
    ]
    menu = InlineKeyboardMarkup(inline_keyboard=menu_buttons)

    result_text = (
        f"📤 Рассылка завершена!\n\n"
        f"✅ Успешно: {success}\n"
        f"❌ Не удалось: {failed}\n"
        f"📊 Охват: {success / total_users * 100:.1f}%"
    )

    await bot.send_message(
        chat_id=query.from_user.id,
        text=result_text,
        reply_markup=menu
    )

    await state.clear()


@router.callback_query(F.data == "admin_cancel")
async def admin_cancel(query: CallbackQuery, state: FSMContext):
    """Отмена рассылки и очистка состояния"""
    data = await state.get_data()

    # Получаем список всех сообщений, которые стоит удалить
    to_delete = data.get("messages_to_delete", [])

    # Добавляем предпросмотр и подтверждение, если есть
    preview_message_id = data.get("preview_message_id")
    confirm_message_id = data.get("confirm_message_id")

    if preview_message_id:
        to_delete.append(preview_message_id)
    if confirm_message_id:
        to_delete.append(confirm_message_id)

    # Удаляем только уникальные и валидные ID
    to_delete = list({mid for mid in to_delete if isinstance(mid, int)})
    await cleanup_chat(query.from_user.id, to_delete)

    await state.clear()

    # Переход в админ-панель
    from main import db
    if db.is_admin(query.from_user.id):
        try:
            from handlers.admin_panel.admin_panel import admin_panel
            await admin_panel(query, state)
        except Exception as e:
            logging.error(f"Ошибка при возврате в админ-панель: {e}")
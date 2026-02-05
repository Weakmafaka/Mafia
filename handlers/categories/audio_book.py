from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaAudio
from aiogram.fsm.context import FSMContext
from utils.library import bot
import logging
import aiohttp
import ssl
import time
from functools import lru_cache
from utils.s3_service import get_files, get_folder_contents, generate_download_url
from handlers.admin_panel.error_notify import notify_admins
from typing import List, Dict, Any, Optional
import asyncio

router = Router()

# Константы для допустимых расширений файлов
ALLOWED_AUDIO_EXTENSIONS = ('.mp3', '.m4a', '.ogg', '.wav')
ALLOWED_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif')
CACHE_TIMEOUT = 3600  # 1 час в секундах
MAX_RETRY_ATTEMPTS = 3  # Максимальное количество попыток отправки файла

def is_audio_file(filename: str) -> bool:
    """Проверяет, является ли файл аудио файлом"""
    return filename.lower().endswith(ALLOWED_AUDIO_EXTENSIONS)

def is_image_file(filename: str) -> bool:
    """Проверяет, является ли файл изображением"""
    return filename.lower().endswith(ALLOWED_IMAGE_EXTENSIONS)
@lru_cache(maxsize=100)
async def get_cached_description(url: str, timestamp: int) -> str:
    """
    Получает кэшированное описание книги
    
    Args:
        url (str): URL файла с описанием
        timestamp (int): Временная метка для инвалидации кэша
        
    Returns:
        str: Текст описания или сообщение об отсутствии описания
    """
    return await read_txt_content(url)

async def read_txt_content(url: str) -> str:
    """
    Читает содержимое txt файла по URL
    
    Args:
        url (str): URL файла для чтения
        
    Returns:
        str: Содержимое файла или сообщение об ошибке
    """
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logging.error(f"Ошибка при получении файла. Статус: {response.status}")
                    return "Описание отсутствует"
    except Exception as e:
        logging.error(f"Ошибка при чтении txt файла: {e}")
        return "Описание отсутствует"

async def send_book(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int) -> None:
    """
    Отправляет список книжных категорий
    
    Args:
        user_id (int): ID пользователя
        state (FSMContext): Состояние FSM
        age_group (str): Возрастная группа
        message_id_to_edit (int): ID сообщения для редактирования
    """
    file_path = f"Контент/{age_group}/Аудиокниги/"
    buttons_data, item_names = await get_files(file_path, age_group, "checkbook_")

    if not item_names:
        logging.warning(f"Не найдены книги для возрастной группы {age_group}")

    await state.update_data(books_item_names=item_names)

    # Преобразуем данные в кнопки
    buttons = [
        InlineKeyboardButton(text=btn['text'], callback_data=btn['callback_data'])
        for btn in buttons_data
    ]

    back_button = InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_main")

    if not buttons:
        text = "К сожалению, книги для этого возраста пока не добавлены. 😔"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
    else:
        text = "Выберите категорию книг которую вы желаете послушать:"
        buttons.append(back_button)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons])

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id_to_edit,
            text=text,
            reply_markup=keyboard
        )
        await state.update_data(message_to_delete=message_id_to_edit)
    except Exception as e:
        logging.error(f"Ошибка при редактировании в send_book: {e}")
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_id_to_edit)
        except Exception as delete_error:
            logging.error(f"Ошибка при удалении сообщения: {delete_error}")
        new_msg = await bot.send_message(user_id, text, reply_markup=keyboard)
        await state.update_data(message_to_delete=new_msg.message_id)

async def send_audio_files(user_id: int, state: FSMContext) -> None:
    """
    Отправляет аудиофайлы книги
    
    Args:
        user_id (int): ID пользователя
        state (FSMContext): Состояние FSM
    """
    data = await state.get_data()
    name = data.get('current_book_name')
    folder_path = data.get('current_book_path')
    files = data.get('book_files')
    
    if not all([name, folder_path, files]):
        logging.error(f"Отсутствуют необходимые данные: name={name}, path={folder_path}, files={bool(files)}")
        await bot.send_message(
            chat_id=user_id,
            text="Произошла ошибка при получении данных книги. Попробуйте выбрать книгу заново.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад к категориям книг", callback_data="menu_books")
            ]])
        )
        return

    media_group = []
    sent_files = 0
    errors = []

    # Проверяем наличие аудиофайлов
    audio_files = [f for f in files if not f['Key'].endswith('/') and is_audio_file(f['Key'].split('/')[-1])]
    if not audio_files:
        logging.error(f"Нет аудиофайлов в книге '{name}' по пути {folder_path}")
        await bot.send_message(
            chat_id=user_id,
            text="В этой книге нет аудиофайлов. Пожалуйста, сообщите администратору.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад к категориям книг", callback_data="menu_books")
            ]])
        )
        await notify_admins(f"Ошибка: В книге '{name}' нет аудиофайлов")
        return

    # Подготавливаем аудиофайлы
    for file_info in audio_files:
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                file_url = await generate_download_url(file_info['Key'])
                audio = InputMediaAudio(
                    media=file_url,
                    caption=f"{name} 🎧" if len(media_group) == 0 else None,
                    title=file_info['Key'].split('/')[-1]
                )
                media_group.append(audio)
                break
            except Exception as e:
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    errors.append(f"Ошибка при подготовке {file_info['Key']}: {str(e)}")
                    logging.error(f"Не удалось подготовить файл после {MAX_RETRY_ATTEMPTS} попыток: {e}")
                else:
                    await asyncio.sleep(1)  # Пауза перед повторной попыткой
                continue

    if media_group:
        total_groups = len(media_group) // 10 + (1 if len(media_group) % 10 else 0)
        status_message = None

        try:
            for i in range(0, len(media_group), 10):
                current_group = i // 10 + 1
                
                if status_message:
                    try:
                        await status_message.edit_text(f"Загружаем книжку \"{name}\"...")
                    except Exception as e:
                        logging.warning(f"Не удалось обновить статус отправки: {e}")
                else:
                    status_message = await bot.send_message(
                        chat_id=user_id,
                        text=f"Загружаем книжку \"{name}\"..."
                    )

                for retry in range(MAX_RETRY_ATTEMPTS):
                    try:
                        await bot.send_media_group(
                            chat_id=user_id,
                            media=media_group[i:i + 10]
                        )
                        sent_files += len(media_group[i:i + 10])
                        break
                    except Exception as e:
                        if retry == MAX_RETRY_ATTEMPTS - 1:
                            logging.error(f"Ошибка при отправке группы аудио: {e}")
                            # Пробуем отправить по одному
                            for audio in media_group[i:i + 10]:
                                try:
                                    await bot.send_audio(
                                        chat_id=user_id,
                                        audio=audio.media,
                                        caption=audio.caption,
                                        title=audio.title
                                    )
                                    sent_files += 1
                                except Exception as single_error:
                                    errors.append(f"Ошибка при отправке {audio.title}: {str(single_error)}")
                        else:
                            await asyncio.sleep(1)  # Пауза перед повторной попыткой
                            continue

        finally:
            if status_message:
                try:
                    await status_message.delete()
                except Exception as e:
                    logging.warning(f"Не удалось удалить сообщение о статусе: {e}")

    if sent_files > 0:
        await bot.send_message(
            chat_id=user_id,
            text=f"Приятного прослушивания книги '{name}' 🎧",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад к категориям книг", callback_data="menu_books")
            ]])
        )
    else:
        error_msg = "\n".join(errors[:3])
        logging.error(f"Не удалось отправить ни одного файла для книги '{name}'. Ошибки: {error_msg}")
        await bot.send_message(
            chat_id=user_id,
            text=f"Не удалось отправить книгу. Пожалуйста, попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад к категориям книг", callback_data="menu_books")
            ]])
        )
        await notify_admins(f"Ошибка⚠️\nНе удалось отправить книгу '{name}'.\nОшибки:\n{error_msg}")

@router.callback_query(lambda c: c.data.startswith('checkbook_'))
async def check_book(query: CallbackQuery, state: FSMContext) -> None:
    """
    Обрабатывает выбор конкретной книжной категории
    
    Args:
        query (CallbackQuery): Объект callback query
        state (FSMContext): Состояние FSM
    """
    try:
        _, index_str, type_age = query.data.split("_")
        item_index = int(index_str)
    except ValueError:
        logging.error(f"Ошибка разбора callback_data в check_books: {query.data}")
        await query.answer("Ошибка данных. Попробуйте еще раз.")
        return

    data = await state.get_data()
    item_names = data.get('books_item_names')

    if not item_names or item_index >= len(item_names):
        logging.error(f"Не найден список имен или индекс вне диапазона: index={item_index}, names={item_names}")
        await query.answer("Ошибка получения данных. Пожалуйста, вернитесь в меню и попробуйте снова.")
        await send_book(query.from_user.id, state, type_age, query.message.message_id)
        return

    name = item_names[item_index]
    folder_path = f"Контент/{type_age}/Аудиокниги/{name}/"

    try:
        loading_message = await query.message.edit_text(f"Загружаем книгу '{name}'... ⏳", reply_markup=None)
    except Exception as e:
        logging.warning(f"Не удалось отредактировать сообщение: {e}")
        loading_message = query.message

    files = await get_folder_contents(folder_path)

    if not files:
        logging.error(f"Не найдены файлы для книги '{name}' по пути {folder_path}")
        await query.answer(f"Книга '{name}' не найдена.", show_alert=True)
        await send_book(query.from_user.id, state, type_age, loading_message.message_id)
        return

    # Проверяем наличие аудиофайлов
    if not any(is_audio_file(f['Key'].split('/')[-1]) for f in files if not f['Key'].endswith('/')):
        logging.error(f"Нет аудиофайлов в книге '{name}' по пути {folder_path}")
        await query.answer("В этой книге нет аудиофайлов", show_alert=True)
        await notify_admins(f"Ошибка: В книге '{name}' нет аудиофайлов")
        await send_book(query.from_user.id, state, type_age, loading_message.message_id)
        return

    await state.update_data(
        current_book_name=name,
        current_book_path=folder_path,
        book_files=files
    )

    poster_url = None
    description = "Описание отсутствует"
    timestamp = int(time.time() / CACHE_TIMEOUT)

    for file_info in files:
        if file_info['Key'].endswith('/'):
            continue

        file_name = file_info['Key'].split('/')[-1].lower()
        if is_image_file(file_name):
            try:
                poster_url = await generate_download_url(file_info['Key'])
            except Exception as e:
                logging.error(f"Ошибка при получении URL постера: {e}")
        elif file_name.endswith('.txt'):
            try:
                description_url = await generate_download_url(file_info['Key'])
                description = await get_cached_description(description_url, timestamp)
            except Exception as e:
                logging.error(f"Ошибка при чтении описания: {e}")

    try:
        if loading_message:
            await bot.delete_message(chat_id=query.from_user.id, message_id=loading_message.message_id)
    except Exception as e:
        logging.error(f"Не удалось удалить сообщение о загрузке: {e}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎧 Слушать книгу", callback_data=f"listen_{name}")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_books")
        ]
    ])

    try:
        if poster_url:
            await bot.send_photo(
                chat_id=query.from_user.id,
                photo=poster_url,
                caption=f"📚 {name}\n\n{description}",
                reply_markup=keyboard
            )
        else:
            await bot.send_message(
                chat_id=query.from_user.id,
                text=f"📚 {name}\n\n{description}",
                reply_markup=keyboard
            )
    except Exception as e:
        logging.error(f"Ошибка при отправке информации о книге '{name}': {e}")
        await bot.send_message(
            chat_id=query.from_user.id,
            text="Произошла ошибка при загрузке информации о книге.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад к категориям книг", callback_data="menu_books")
            ]])
        )

@router.callback_query(lambda c: c.data.startswith('listen_'))
async def listen_book(query: CallbackQuery, state: FSMContext) -> None:
    """
    Обработчик нажатия на кнопку 'Слушать книгу'
    
    Args:
        query (CallbackQuery): Объект callback query
        state (FSMContext): Состояние FSM
    """
    await query.answer()
    
    try:
        await query.message.delete()
    except Exception as e:
        logging.error(f"Ошибка при удалении сообщения с постером: {e}")
    
    await send_audio_files(query.from_user.id, state)
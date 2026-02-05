import os
from datetime import date
import base64 # Добавляем импорт base64
import io     # Добавляем импорт io
import httpx  # Добавляем импорт httpx

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from openai import AsyncOpenAI, OpenAIError
from dotenv import load_dotenv

from Database.database import Database
from utils.library import bot # Импортируем bot из library

from handlers.admin_panel.error_notify import notify_admins
load_dotenv()

# Устанавливаем переменные окружения для прокси
os.environ["HTTP_PROXY"] = "http://EHC26y17:FvCFnEHF@172.120.185.111:64786"
os.environ["HTTPS_PROXY"] = "http://EHC26y17:FvCFnEHF@172.120.185.111:64786"

# Инициализация OpenAI клиента
http_client = httpx.AsyncClient()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)

# Инициализация базы данных (предполагаем, что она синглтон или передается)
db = Database()

router = Router()

# Константы
SUBSCRIBED_LIMIT = 5
NON_SUBSCRIBED_LIMIT = 5
SYSTEM_PROMPT = """Ты — дружелюбный и полезный AI-помощник по имени Янтарик. Ты общаешься с мамами и помогаешь им с различными вопросами:
- Воспитание и развитие детей разного возраста.
- Помощь с детскими вопросами и домашними заданиями.
- Идеи для игр и занятий с детьми.
- Генерация идей для поделок, раскрасок.
- Простые рецепты для детей.
- Поддержка и советы для мам.
Ты отвечаешь на русском языке, понятно и позитивно. Избегай сложных терминов. Будь эмпатичным и поддерживающим."""

# Состояния FSM
class AIState(StatesGroup):
    in_conversation = State()

# Клавиатура для выхода из режима AI
finish_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Завершить диалог")]],
    resize_keyboard=True,
    one_time_keyboard=False # Оставляем клавиатуру видимой
)

async def check_and_update_usage(user_id: int) -> bool:
    """Проверяет лимит запросов и обновляет счетчик. Возвращает True, если лимит не превышен."""
    user = db.get_user(user_id)
    if not user:
        # На всякий случай, если пользователя нет в БД
        db.add_user(user_id)
        user = db.get_user(user_id)

    is_subscriber = db.is_subscribed(user_id)
    limit = SUBSCRIBED_LIMIT if is_subscriber else NON_SUBSCRIBED_LIMIT
    
    today = date.today()
    usage_count = db.get_ai_usage(user_id, today)

    if usage_count >= limit:
        return False # Лимит превышен

    db.increment_ai_usage(user_id, today)
    return True # Лимит не превышен

@router.callback_query(F.data == "ai_assistant")
async def start_ai_assistant(query: CallbackQuery, state: FSMContext):
    """Обработчик входа в режим AI-помощника."""
    user_id = query.from_user.id
    
    # Проверка на премиум подписку
    # from main import db
    # is_premium = db.check_premium_status(user_id)
    #
    # if not is_premium:
    #     await query.answer("AI помощник доступен только для пользователей с премиум подпиской", show_alert=True)
    #     return
 
    # Обновляем время последней активности
    db.update_user_activity(user_id)
    
    await state.set_state(AIState.in_conversation)
    
    # Удаляем предыдущее сообщение с инлайн-клавиатурой
    try:
        await query.message.delete()
    except TelegramBadRequest as e:
        print(f"Не удалось удалить предыдущее сообщение: {e}")
    except Exception as e:
        print(f"Непредвиденная ошибка при удалении сообщения: {e}")

    # Отправляем новое приветственное сообщение с ReplyKeyboard
    await query.message.answer( # Используем answer для отправки в тот же чат
        "👋 Привет-привет! Я Янтарик — твой весёлый AI-помощник 🤖✨\n"
        "Я могу:\n"
        "• Помочь с детскими вопросами 👶\n"
        "• Подкинуть идею для игры 🎲\n"
        "• Помочь с домашкой 📚\n"
        "• Нарисовать классную раскраску — просто напиши 'Нарисуй' и что хочешь увидеть! 🎨\n"
        f"У тебя есть {SUBSCRIBED_LIMIT} запросов в день. Используй их с умом!\n"
        "Чтобы выйти, жми кнопку внизу 👇",
        reply_markup=finish_keyboard
    )

    await query.answer() # Закрываем уведомление о нажатии кнопки

@router.message(AIState.in_conversation, F.text == "Завершить диалог")
async def finish_ai_conversation(message: Message, state: FSMContext):
    """Обработчик кнопки 'Завершить диалог'."""
    # Импортируем show_main_menu здесь
    from handlers.common import show_main_menu
    
    user_id = message.from_user.id
    await state.clear()
    await message.answer("Рад был помочь! Возвращаю в главное меню.", reply_markup=ReplyKeyboardRemove())
    
    # Получаем возраст пользователя
    age_group = db.get_user_age(user_id)
    
    if age_group:
        # Показываем главное меню с правильными аргументами
        await show_main_menu(user_id=user_id, age_group=age_group, state=state)
    else:
        # Если возраст не найден
        await message.answer("Не удалось определить вашу возрастную группу. Пожалуйста, используйте /start для настройки.")

@router.message(AIState.in_conversation, F.text & ~F.text.startswith('/')) # Обрабатываем текст, кроме команд
async def handle_text_message(message: Message, state: FSMContext):
    """Обработка текстовых сообщений в режиме AI."""
    user_id = message.from_user.id
    
    # Обновляем время последней активности
    from main import db
    db.update_user_activity(user_id)
    
    # Проверка лимита на каждый запрос
    if not await check_and_update_usage(user_id):
        await message.reply(f"Извините, вы достигли дневного лимита в {SUBSCRIBED_LIMIT} запросов к AI-помощнику. Попробуйте завтра.")
        return

    # Проверка на команду рисования
    if "нарисуй" in message.text.lower():
        prompt_text = message.text.lower().replace("нарисуй", "").strip()
        if not prompt_text:
             await message.reply("Пожалуйста, укажите, что нужно нарисовать после слова 'Нарисуй'.")
             return
             
        await message.reply("🎨 Понял! Начинаю рисовать...")
        try:
            response = await client.images.generate(
                model="dall-e-3",
                prompt=f"Детский рисунок или раскраска в простом стиле: {prompt_text}", # Уточняем стиль
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            # Отправляем изображение по URL
            await bot.send_photo(chat_id=user_id, photo=image_url, caption=f"Вот что у меня получилось по запросу: '{prompt_text}'")
        except Exception as e:
            print(f"Ошибка генерации изображения DALL-E: {e}")
            await message.reply("😔 Упс! Что-то пошло не так при рисовании. Попробуйте переформулировать запрос.")
        return # Выходим после обработки рисования

    # Сохраняем сообщение "Думаю..."
    thinking_message = await message.reply("⏳ Думаю над вашим вопросом...") 
    
    ai_response = None # Инициализируем переменную для ответа
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini", # Или другая модель, например gpt-3.5-turbo
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.text}
            ],
            max_tokens=1000
        )
        ai_response = response.choices[0].message.content
        # Отправляем ответ AI
        await message.reply(ai_response)


    except httpx.HTTPStatusError as http_err:
        if http_err.response.status_code == 402:
            error = "Критическая ошибка\nЗакончился баланс на сервере AI."
        else:
            error = f"Критическая ошибка\nHTTP ошибка AI: {http_err}"
        await notify_admins(error)
        await message.reply("😔 Ой! Кажется, я немного заблудился в мыслях. Попробуйте спросить еще раз чуть позже.")

    except OpenAIError as openai_err:
        error_text = str(openai_err)
        if "insufficient_quota" in error_text.lower():
            error = "Критическая ошибка\nПревышен лимит AI: insufficient_quota"
        else:
            error = f"Критическая ошибка\nOpenAI API ошибка: {openai_err}"
        await notify_admins(error)
        await message.reply("😔 Ой! Кажется, я немного заблудился в мыслях. Попробуйте спросить еще раз чуть позже.")

    except Exception as e:
        error_text = str(e)
        if "insufficient_quota" in error_text.lower():
            error = "Критическая ошибка\nПревышен лимит AI: insufficient_quota"
        else:
            error = f"Критическая ошибка\nНеизвестная ошибка: {e}"
        await notify_admins(error)
        await message.reply("😔 Ой! Кажется, я немного заблудился в мыслях. Попробуйте спросить еще раз чуть позже.")

    finally:
        # В любом случае (успех или ошибка), пытаемся удалить сообщение "Думаю..."
        try:
            await thinking_message.delete()
        except TelegramBadRequest as e:
            # Ошибка может возникнуть, если сообщение уже удалено или слишком старое
            print(f"Не удалось удалить сообщение 'Думаю...': {e}")
        except Exception as e:
            # Другие возможные ошибки при удалении
             print(f"Непредвиденная ошибка при удалении сообщения 'Думаю...': {e}")


@router.message(AIState.in_conversation, F.photo)
async def handle_photo_message(message: Message, state: FSMContext):
    """Обработка сообщений с фото в режиме AI (с использованием Vision модели)."""
    user_id = message.from_user.id
    
    # Проверка лимита
    if not await check_and_update_usage(user_id):
        await message.reply(f"Извините, вы достигли дневного лимита в {SUBSCRIBED_LIMIT} запросов к AI-помощнику. Попробуйте завтра.")
        return

    # Сообщение о том, что фото получено и обрабатывается
    thinking_message = await message.reply("🖼️ Фото получил! 🤔 Думаю над вашим вопросом к фото...")
    
    photo = message.photo[-1] # Берем фото наибольшего разрешения
    prompt_text = message.caption if message.caption else "Опиши это изображение подробно."
    
    # Проверка на команду рисования в подписи (даже если работаем с фото)
    if message.caption and "нарисуй" in message.caption.lower():
        await thinking_message.edit_text("Я пока не умею рисовать на основе фото. Могу только по текстовому описанию после слова 'Нарисуй'.")
        return # Выходим, не делая запрос к vision

    base64_image = None
    ai_response = None
    try:
        # Скачиваем фото в память
        with io.BytesIO() as photo_stream:
            await bot.download(file=photo.file_id, destination=photo_stream)
            photo_bytes = photo_stream.getvalue()
        
        # Кодируем в base64
        base64_image = base64.b64encode(photo_bytes).decode('utf-8')
        
        # Формируем запрос к Vision модели
        response = await client.chat.completions.create(
            model="gpt-4o", # Используем модель с Vision
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}" # Предполагаем JPEG
                            },
                        },
                    ],
                }
            ],
            max_tokens=1000
        )
        ai_response = response.choices[0].message.content
        # Отправляем ответ AI
        await message.reply(ai_response)


    except httpx.HTTPStatusError as http_err:
        if http_err.response.status_code == 402:
            error = "Критическая ошибка\nЗакончился баланс на сервере AI."
        else:
            error = f"Критическая ошибка\nHTTP ошибка AI: {http_err}"
        await notify_admins(error)
        await message.reply(
            "😔 Ой! Что-то пошло не так при анализе изображения. Попробуйте отправить изображение позже.")

    except OpenAIError as openai_err:
        error_text = str(openai_err)
        if "insufficient_quota" in error_text.lower():
            error = "Критическая ошибка\nПревышен лимит AI: insufficient_quota"
        else:
            error = f"Критическая ошибка\nOpenAI API ошибка: {openai_err}"
        await notify_admins(error)
        await message.reply(
            "😔 Ой! Что-то пошло не так при анализе изображения. Попробуйте отправить изображение позже.")

    except Exception as e:
        error_text = str(e)
        if "insufficient_quota" in error_text.lower():
            error = "Критическая ошибка\nПревышен лимит AI: insufficient_quota"
        else:
            error = f"Критическая ошибка\nНеизвестная ошибка: {e}"
        await notify_admins(error)
        await message.reply("😔 Ой! Что-то пошло не так при анализе изображения. Попробуйте отправить изображение позже.")
    finally:
        # Удаляем сообщение "Думаю..."
        try:
            await thinking_message.delete()
        except Exception as del_e:
            print(f"Не удалось удалить сообщение 'Думаю над фото...': {del_e}")
        # Очищаем переменную с base64 на всякий случай (хотя она и так локальная)
        base64_image = None


@router.message(AIState.in_conversation, F.voice)
async def handle_voice_message(message: Message, state: FSMContext):
    """Обработка голосовых сообщений в режиме AI."""
    user_id = message.from_user.id

    if not await check_and_update_usage(user_id):
        await message.reply(
            f"Извините, вы достигли дневного лимита в {SUBSCRIBED_LIMIT} запросов к AI-помощнику. Попробуйте завтра.")
        return

    await message.reply("🎤 Голосовое сообщение получил! Сейчас расшифрую и подумаю...")

    voice_ogg_path = f"voice_{user_id}.ogg"

    try:
        # Скачиваем голосовое сообщение
        voice_file_info = await bot.get_file(message.voice.file_id)
        await bot.download_file(voice_file_info.file_path, destination=voice_ogg_path)

        # Отправляем в Whisper
        with open(voice_ogg_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        transcribed_text = transcript.text
        os.remove(voice_ogg_path)

        await message.reply(f"Я расслышал: '{transcribed_text}'. Теперь отвечаю...")

        # Проверка на команду рисования
        if "нарисуй" in transcribed_text.lower():
            prompt_text = transcribed_text.lower().replace("нарисуй", "").strip()
            if not prompt_text:
                await message.reply("Пожалуйста, укажите, что нужно нарисовать после слова 'Нарисуй'.")
                return
            await message.reply("🎨 Понял! Начинаю рисовать...")
            try:
                response = await client.images.generate(
                    model="dall-e-3",
                    prompt=f"Детский рисунок или раскраска в простом стиле: {prompt_text}",
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
                image_url = response.data[0].url
                await bot.send_photo(chat_id=user_id, photo=image_url,
                                     caption=f"Вот что у меня получилось по запросу: '{prompt_text}'")
            except Exception as e:
                await notify_admins(f"Критическая ошибка\nОшибка генерации изображения DALL-E (voice): {e}")
                await message.reply("😔 Упс! Что-то пошло не так при рисовании. Попробуйте переформулировать запрос.")
            return

        # GPT-ответ
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcribed_text}
            ],
            max_tokens=1000
        )
        ai_response = response.choices[0].message.content
        await message.reply(ai_response)

    except httpx.HTTPStatusError as http_err:
        if http_err.response.status_code == 402:
            error = "Критическая ошибка\nЗакончился баланс на сервере AI."
        else:
            error = f"Критическая ошибка\nHTTP ошибка AI: {http_err}"
        await notify_admins(error)
        await message.reply("😔 Ой! Что-то пошло не так при обработке голосового сообщения. Попробуйте чуть позже.")

    except OpenAIError as openai_err:
        error_text = str(openai_err)
        if "insufficient_quota" in error_text.lower():
            error = "Критическая ошибка\nПревышен лимит AI: insufficient_quota"
        else:
            error = f"Критическая ошибка\nOpenAI API ошибка: {openai_err}"
        await notify_admins(error)
        await message.reply("😔 Ой! Что-то пошло не так при обработке голосового сообщения. Попробуйте чуть позже.")

    except Exception as e:
        error_text = str(e)
        if "insufficient_quota" in error_text.lower():
            error = "Критическая ошибка\nПревышен лимит AI: insufficient_quota"
        else:
            error = f"Критическая ошибка\nНеизвестная ошибка (voice): {e}"
        await notify_admins(error)
        await message.reply("😔 Ой! Что-то пошло не так при обработке голосового сообщения. Попробуйте чуть позже.")

    finally:
        if os.path.exists(voice_ogg_path):
            try:
                os.remove(voice_ogg_path)
            except Exception as del_err:
                print(f"Ошибка удаления временного файла {voice_ogg_path}: {del_err}")

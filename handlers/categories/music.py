from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaAudio
from aiogram.fsm.context import FSMContext
from utils.library import bot
import logging
from utils.s3_service import get_files, get_folder_contents, generate_download_url

from handlers.admin_panel.error_notify import notify_admins

router = Router()


async def send_music(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int):
    """Отправляет список музыкальных категорий"""
    file_path = f"Контент/{age_group}/Музыка/"
    buttons_data, item_names = await get_files(file_path, age_group, "checkmusic_")

    await state.update_data(music_item_names=item_names)

    # Преобразуем данные в кнопки
    buttons = [
        InlineKeyboardButton(text=btn['text'], callback_data=btn['callback_data'])
        for btn in buttons_data
    ]

    back_button = InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_main")

    if not buttons:
        text = "К сожалению, музыка для этого возраста пока не добавлена. 😔"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
    else:
        text = "Выберите категорию музыки которую вы желаете послушать:"
        buttons.append(back_button)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id_to_edit,
            text=text,
            reply_markup=keyboard
        )
        await state.update_data(message_to_delete=message_id_to_edit)
    except Exception as e:
        logging.error(f"Ошибка при редактировании в send_music: {e}")
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_id_to_edit)
        except Exception:
            pass
        new_msg = await bot.send_message(user_id, text, reply_markup=keyboard)
        await state.update_data(message_to_delete=new_msg.message_id)


@router.callback_query(lambda c: c.data.startswith('checkmusic_'))
async def check_music(query: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор конкретной музыкальной категории"""
    final_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к категориям музыки", callback_data="menu_music")]
        ]
    )

    try:
        # Пытаемся ответить на callback query в начале
        await query.answer()
        
        _, index_str, type_age = query.data.split("_")
        item_index = int(index_str)
    except ValueError:
        logging.error(f"Ошибка разбора callback_data в check_music: {query.data}")
        await query.answer("Ошибка данных. Попробуйте еще раз.")
        return

    data = await state.get_data()
    item_names = data.get('music_item_names')

    if not item_names or item_index >= len(item_names):
        logging.error(f"Не найден список имен или индекс вне диапазона: index={item_index}, names={item_names}")
        await query.answer("Ошибка получения данных. Пожалуйста, вернитесь в меню и попробуйте снова.")
        await send_music(query.from_user.id, state, type_age, query.message.message_id)
        return

    name = item_names[item_index]
    folder_path = f"Контент/{type_age}/Музыка/{name}/"

    loading_message = None

    try:
        loading_message = await query.message.edit_text(f"Загружаем музыку '{name}'... ⏳", reply_markup=None)
    except Exception as e:
        logging.warning(f"Не удалось отредактировать сообщение: {e}")
        loading_message = query.message

    try:
        files = await get_folder_contents(folder_path)

        if not files:
            await query.answer(f"Музыка '{name}' не найдена.", show_alert=True)
            await send_music(query.from_user.id, state, type_age, loading_message.message_id)
            return

        sent_files = 0
        errors = []
        media_group = []

        for file_info in files:
            if file_info['Key'].endswith('/'):
                continue

            try:
                file_url = await generate_download_url(file_info['Key'])
                logging.info(f"Подготовка файла для отправки: {file_url}")

                # Создаем объект аудио для медиагруппы
                audio = InputMediaAudio(
                    media=file_url,
                    caption=f"{name} 🎶" if len(media_group) == 0 else None,
                    title=file_info['Key'].split('/')[-1]
                )
                media_group.append(audio)

            except Exception as e:
                errors.append(f"Ошибка при подготовке {file_info['Key']}: {str(e)}")
                continue

        # Удаляем сообщение "Загружаем музыку..."
        try:
            if loading_message:
                await bot.delete_message(chat_id=query.from_user.id, message_id=loading_message.message_id)
        except Exception as e:
            logging.error(f"Не удалось удалить сообщение о загрузке: {e}")

        if media_group:
            try:
                # Отправляем все аудио одной группой (максимум 10 файлов за раз)
                for i in range(0, len(media_group), 10):
                    await bot.send_media_group(
                        chat_id=query.from_user.id,
                        media=media_group[i:i + 10]
                    )
                    sent_files += len(media_group[i:i + 10])

                # Отправляем финальное сообщение с клавиатурой
                await bot.send_message(
                    chat_id=query.from_user.id,
                    text=f"Вот ваша музыка из категории '{name}' 🎶",
                    reply_markup=final_keyboard
                )

            except Exception as e:
                logging.error(f"Ошибка при отправке медиагруппы: {e}")
                errors.append(f"Ошибка при отправке группы аудио: {str(e)}")

                # Если не удалось отправить группой, пробуем отправить по одному
                for audio in media_group:
                    try:
                        await bot.send_audio(
                            chat_id=query.from_user.id,
                            audio=audio.media,
                            caption=audio.caption,
                            title=audio.title
                        )
                        sent_files += 1
                    except Exception as e:
                        errors.append(f"Ошибка при отправке {audio.title}: {str(e)}")

                if sent_files > 0:
                    await bot.send_message(
                        chat_id=query.from_user.id,
                        text=f"Часть музыки из категории '{name}' 🎶",
                        reply_markup=final_keyboard
                    )

        if sent_files == 0:
            error_msg = "\n".join(errors[:3])
            await bot.send_message(
                chat_id=query.from_user.id,
                text=f"Не удалось отправить музыку.",
                reply_markup=final_keyboard
            )
            await notify_admins(f"Ошибка⚠️\nНе удалось отправить музыку.\nОшибки:\n{error_msg}")

    except Exception as e:
        logging.error(f"Ошибка при обработке кнопки музыки: {e}")
        await notify_admins(f"Критическая ошибка\nПри обработке кнопки в разделе Музыка: {e}")
        # Показываем пользователю дружелюбное сообщение
        try:
            back_button = InlineKeyboardButton(text="◀️ Назад", callback_data=f"music_{type_age}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
            await bot.send_message(
                chat_id=query.from_user.id,
                text="Извините, произошла ошибка при загрузке музыки. Пожалуйста, попробуйте еще раз.",
                reply_markup=keyboard
            )
        except Exception as send_error:
            logging.error(f"Не удалось отправить сообщение об ошибке: {send_error}")
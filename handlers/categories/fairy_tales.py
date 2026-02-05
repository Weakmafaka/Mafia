from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from utils.library import bot
import logging
from utils.s3_service import get_files, get_folder_contents, generate_download_url
from handlers.admin_panel.error_notify import notify_admins

router = Router()


async def send_fairy(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int):
    """Отправляет список доступных сказок"""
    file_path = f"Контент/{age_group}/Сказки/"
    buttons_data, item_names = await get_files(file_path, age_group, "checkfairy_")

    await state.update_data(fairy_item_names=item_names)

    # Преобразуем данные в кнопки
    buttons = [
        InlineKeyboardButton(text=btn['text'], callback_data=btn['callback_data'])
        for btn in buttons_data
    ]

    back_button = InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_main")

    if not buttons:
        text = "К сожалению, сказки для этого возраста пока не добавлены. 😔"
        await notify_admins(f"Ошибка\nСказки для возраста {age_group} не добавлены")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
    else:
        text = "Выберите сказку для прослушивания:"
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
        logging.error(f"Ошибка при редактировании в send_fairy: {e}")
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_id_to_edit)
        except Exception:
            pass
        new_msg = await bot.send_message(user_id, text, reply_markup=keyboard)
        await state.update_data(message_to_delete=new_msg.message_id)


@router.callback_query(lambda c: c.data.startswith('checkfairy_'))
async def check_fairy(query: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор конкретной сказки"""
    final_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к сказкам", callback_data="menu_fairy_tales")]
        ]
    )

    try:
        # Пытаемся ответить на callback query в начале
        await query.answer()
        
        _, index_str, type_age = query.data.split("_")
        item_index = int(index_str)
    except ValueError:
        error = f"Ошибка разбора callback_data в check_fairy: {query.data}"
        logging.error(error)
        await notify_admins(f"Критическая ошибка\n{error}")
        await query.answer("Ошибка данных. Попробуйте еще раз.")
        return

    data = await state.get_data()
    item_names = data.get('fairy_item_names')

    if not item_names or item_index >= len(item_names):
        logging.error(f"Не найден список имен или индекс вне диапазона: index={item_index}, names={item_names}")
        await query.answer("Ошибка получения данных. Пожалуйста, вернитесь в меню и попробуйте снова.")
        await send_fairy(query.from_user.id, state, type_age, query.message.message_id)
        return

    name = item_names[item_index]
    folder_path = f"Контент/{type_age}/Сказки/{name}/"

    # Сохраняем сообщение "Загружаем сказку..." для последующего удаления
    loading_message = None

    try:
        loading_message = await query.message.edit_text(f"Загружаем сказку '{name}'... ⏳", reply_markup=None)
    except Exception as e:
        logging.warning(f"Не удалось отредактировать сообщение: {e}")
        loading_message = query.message

    try:
        files = await get_folder_contents(folder_path)

        if not files:
            await query.answer(f"Сказка '{name}' не найдена.", show_alert=True)
            await notify_admins(f"Ошибка\nСказка {name} в возрасте {type_age} не найдена")
            await send_fairy(query.from_user.id, state, type_age, loading_message.message_id)
            return

        sent_files = 0
        errors = []

        for file_info in files:
            if file_info['Key'].endswith('/'):  # Пропускаем директории
                continue

            try:
                file_url = await generate_download_url(file_info['Key'])
                logging.info(f"Пытаемся отправить аудиофайл: {file_url}")

                await bot.send_audio(
                    chat_id=query.from_user.id,
                    audio=file_url,
                    title=file_info['Key'].split('/')[-1]
                )
                sent_files += 1
            except Exception as e:
                errors.append(f"Ошибка при отправке {file_info['Key']}: {str(e)}")
                continue

        # Удаляем сообщение "Загружаем сказку..."
        try:
            if loading_message:
                await bot.delete_message(chat_id=query.from_user.id, message_id=loading_message.message_id)
        except Exception as e:
            logging.error(f"Не удалось удалить сообщение о загрузке: {e}")

        if sent_files > 0:
            await bot.send_message(
                chat_id=query.from_user.id,
                text=f"Вот ваша сказка – {name} 🎧",
                reply_markup=final_keyboard
            )
        else:
            error_msg = "\n".join(errors[:3])
            await bot.send_message(
                chat_id=query.from_user.id,
                text=f"Не удалось отправить сказку.",
                reply_markup=final_keyboard
            )
            await notify_admins(f"Ошибка\nНе удалось отправить сказку {error_msg}")

    except Exception as e:
        logging.error(f"Ошибка при обработке кнопки сказок: {e}")
        await notify_admins(f"Критическая ошибка\nПри обработке кнопки в разделе Сказки: {e}")
        # Показываем пользователю дружелюбное сообщение
        try:
            back_button = InlineKeyboardButton(text="◀️ Назад", callback_data=f"fairy_{type_age}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
            await bot.send_message(
                chat_id=query.from_user.id,
                text="Извините, произошла ошибка при загрузке сказки. Пожалуйста, попробуйте еще раз.",
                reply_markup=keyboard
            )
        except Exception as send_error:
            logging.error(f"Не удалось отправить сообщение об ошибке: {send_error}")
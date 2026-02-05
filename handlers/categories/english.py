from aiogram import Router, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext

from utils.library import bot
import logging

router = Router()


async def english(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int):
    """Отображает меню с кнопками для запуска игр Mini Apps english."""

    text = "Выберите игру, в которую хотите сыграть:"

    # Создаем кнопки с Mini Apps
    games_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
             InlineKeyboardButton(text="🔤Алфавит",
                                  callback_data="game_english_0"),
            InlineKeyboardButton(text="🔢Цифры",
                                 callback_data="game_english_1")
        ],
        [
            InlineKeyboardButton(text="👋 Приветствие",
                                 callback_data="game_english_2"),
            InlineKeyboardButton(text="🧍Части тела",
                                 callback_data="game_english_3")
        ],
        [
            InlineKeyboardButton(text="🎨Цвета",
                                 callback_data="game_english_4"),
            InlineKeyboardButton(text="🌞Времена года",
                                 callback_data="game_english_5")],
            # [InlineKeyboardButton(text="📚Грамматика",
            #                       callback_data="game_english_6"),
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


@router.callback_query(lambda c: c.data.startswith('game_english'))
async def test_english(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    message_edit = data.get('message_to_delete')

    _, index_str, type_game = query.data.split("_")

    game_url = None
    text = None
    photo = None
    video_url = None

    if type_game == "0":
        game_url = "https://wordwall.net/ru/resource/28764989/english/alphabet-maze-chase-15-letters-myteachingstuff"
        video_url = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%90%D0%BB%D1%84%D0%B0%D0%B2%D0%B8%D1%82/%D0%90%D0%BB%D1%84%D0%B0%D0%B2%D0%B8%D1%82.mp4"
        text = "В данном уроке ваш ребенок выучит английский алфавит 🎉"
        photo = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%90%D0%BB%D1%84%D0%B0%D0%B2%D0%B8%D1%82/alphabet.jpg"
    elif type_game == "1":
        game_url = "https://wordwall.net/resource/75086813/%d0%b0%d0%bd%d0%b3%d0%bb%d0%b8%d0%b9%d1%81%d0%ba%d0%b8%d0%b9/lets-count"
        video_url = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%A6%D0%B8%D1%84%D1%80%D1%8B/%D0%A6%D0%B8%D1%84%D1%80%D1%8B.mp4"
        text = "В данном уроке ваш ребенок выучит произношение цифр на английском языке 🎉"
        photo = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%A6%D0%B8%D1%84%D1%80%D1%8B/numbers.jpg"
    elif type_game == "2":
        game_url = "https://wordwall.net/ru/resource/35823394/%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82%D1%81%D1%82%D0%B2%D0%B8%D0%B5-%D0%B8-%D0%BF%D1%80%D0%BE%D1%89%D0%B0%D0%BD%D0%B8%D0%B5-%D0%BD%D0%B0-%D0%B0%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%BE%D0%BC-%D1%8F%D0%B7%D1%8B%D0%BA%D0%B5"
        video_url = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82%D1%81%D1%82%D0%B2%D0%B8%D0%B5/Hello%21%20_%20Kids%20Greeting%20Song%20and%20Feelings%20Song%20_%20Super%20Simple%20Songs.mp4"
        text = "В данном уроке ваш ребенок научится различным приветствиям на английском языке 🎉"
        photo = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82%D1%81%D1%82%D0%B2%D0%B8%D0%B5/greetings.jpeg"
    elif type_game == "3":
        game_url = "https://wordwall.net/ru/resource/16400914"
        video_url = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%A7%D0%B0%D1%81%D1%82%D0%B8%20%D1%82%D0%B5%D0%BB%D0%B0/Learn%20Parts%20of%20Body.mp4"
        text = "В данном уроке ваш ребенок научится называть разные части тела на английском языке 🎉"
        photo = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%A7%D0%B0%D1%81%D1%82%D0%B8%20%D1%82%D0%B5%D0%BB%D0%B0/bodyparts.jpg"
    elif type_game == "4":
        game_url = "https://wordwall.net/ru/resource/540697/%D1%86%D0%B2%D0%B5%D1%82%D0%B0"
        video_url = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%A6%D0%B2%D0%B5%D1%82%D0%B0/Learn%20Colors%20-%20Preschool%20Chant%20-%20Colors%20Song%20for%20Preschool%20by%20ELF%20Learning%20-%20ELF%20Kids%20Videos%20%281%29.mp4"
        text = "В данном уроке ваш ребенок выучит различные цвета на английском языке 🎉"
        photo = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%A6%D0%B2%D0%B5%D1%82%D0%B0/colors.jpg"
    elif type_game == "5":
        game_url = "https://wordwall.net/ru/resource/74736583/%d0%b0%d0%bd%d0%b3%d0%bb%d0%b8%d0%b9%d1%81%d0%ba%d0%b8%d0%b9/%d0%b7%d0%b0%d0%b4%d0%b0%d0%bd%d0%b8%d0%b5-%d0%bf%d0%be-%d1%82%d0%b5%d0%bc%d0%b5-%d0%b2%d1%80%d0%b5%d0%bc%d0%b5%d0%bd%d0%b0-%d0%b3%d0%be%d0%b4%d0%b0"
        video_url = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%A6%D0%B2%D0%B5%D1%82%D0%B0/Learn%20colors.mp4"
        text = "В данном уроке ваш ребенок научится произносить времена года на английском языке 🎉"
        photo = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%92%D1%80%D0%B5%D0%BC%D0%B5%D0%BD%D0%B0%20%D0%B3%D0%BE%D0%B4%D0%B0/seasons.jpg"

    elif type_game == "6":
        game_url = "https://wordwall.net/ru/resource/74736583/%d0%b0%d0%bd%d0%b3%d0%bb%d0%b8%d0%b9%d1%81%d0%ba%d0%b8%d0%b9/%d0%b7%d0%b0%d0%b4%d0%b0%d0%bd%d0%b8%d0%b5-%d0%bf%d0%be-%d1%82%d0%b5%d0%bc%d0%b5-%d0%b2%d1%80%d0%b5%d0%bc%d0%b5%d0%bd%d0%b0-%d0%b3%d0%be%d0%b4%d0%b0"
        video_url = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%A6%D0%B2%D0%B5%D1%82%D0%B0/Learn%20colors.mp4"
        text = "В данном уроке ваш ребенок научится произносить времена года на английском языке 🎉"
        photo = "https://s3.regru.cloud/yantarik/%D0%9A%D0%BE%D0%BD%D1%82%D0%B5%D0%BD%D1%82/7-10/%D0%90%D0%BD%D0%B3%D0%BB%D0%B8%D0%B9%D1%81%D0%BA%D0%B8%D0%B9%20%D1%8F%D0%B7%D1%8B%D0%BA/%D0%92%D1%80%D0%B5%D0%BC%D0%B5%D0%BD%D0%B0%20%D0%B3%D0%BE%D0%B4%D0%B0/seasons.jpg"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Обучение 📚",
                                 web_app=WebAppInfo(url=video_url))
        ],
        [
            InlineKeyboardButton(text="Практическая 🏁",
                                 web_app=WebAppInfo(url=game_url))
        ],
        [
            InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_eng")
        ]
    ])

    try:
        # Пытаемся редактировать существующее сообщение
        await bot.edit_message_media(
            chat_id=query.from_user.id,
            message_id=message_edit,
            media=InputMediaPhoto(
                media=photo,
                caption=text
            ),
            reply_markup=keyboard
        )
    except Exception as e:
        # Если не получилось редактировать (например, сообщение не содержит медиа)
        try:
            await bot.edit_message_caption(
                chat_id=query.from_user.id,
                message_id=message_edit,
                caption=text,
                reply_markup=keyboard
            )
        except Exception as e:
            # Если совсем не получается редактировать, отправляем новое сообщение
            print(f"Ошибка при редактировании: {e}")
            msg = await bot.send_photo(
                chat_id=query.from_user.id,
                photo=photo,
                caption=text,
                reply_markup=keyboard
            )
            await state.update_data(message_to_delete=msg.message_id)


@router.callback_query(F.data == "back_to_eng")
async def back_to_eng(query : CallbackQuery, state : FSMContext):
    age = "None"
    message_id_to_edit = query.message.message_id
    await english(query.from_user.id, state, age, message_id_to_edit)
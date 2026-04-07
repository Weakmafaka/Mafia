import io
import os
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select, update

from database.controllers.ui_state import set_menu_message_id
from database.database import db
from database.models.user import User
from core.telegram import bot

router = Router()


class SettingsState(StatesGroup):
    waiting_nickname = State()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Настройки", callback_data="menu_settings"),
                InlineKeyboardButton(text="Начать игру", callback_data="menu_start_game"),
            ],
            [
                InlineKeyboardButton(text="Рейтинг", callback_data="menu_rating"),
                InlineKeyboardButton(text="Правила", callback_data="menu_rules"),
            ],
        ]
    )


def settings_keyboard(notifications_enabled: bool) -> InlineKeyboardMarkup:
    notif_text = "Рассылка: Вкл" if notifications_enabled else "Рассылка: Выкл"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=notif_text, callback_data="settings_toggle_notifications")],
            [InlineKeyboardButton(text="Сменить никнейм", callback_data="settings_change_nickname")],
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def nickname_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="back_main")],
        ]
    )


def role_stats_line(user: User) -> str:
    games = max(user.games_played, 1)
    mafia_pct = round((user.mafia_wins / games) * 100, 1)
    civilian_pct = round((user.civilian_wins / games) * 100, 1)
    if mafia_pct >= civilian_pct:
        return "Лучше за мафию: {}% побед".format(mafia_pct)
    return "Лучше за мирных: {}% побед".format(civilian_pct)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_candidates:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def build_profile_image(user: User, nickname: str) -> BufferedInputFile:
    games = user.games_played
    wins = user.wins
    losses = user.losses
    total_for_rate = max(games, 1)
    win_rate = round((wins / total_for_rate) * 100, 1)
    lose_rate = round((losses / total_for_rate) * 100, 1)

    image = Image.new("RGB", (1200, 628), color="white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(62, bold=True)
    text_font = load_font(42)
    small_font = load_font(36)
    lines = [
        "MAFIA BOT PROFILE",
        "",
        "Никнейм: {}".format(nickname),
        "Игр сыграно: {}".format(games),
        "Рейтинг: {}".format(user.rating),
        "Победы: {}% | Поражения: {}%".format(win_rate, lose_rate),
        role_stats_line(user),
    ]
    y = 50
    for index, line in enumerate(lines):
        fill = "black" if index else "#222222"
        if index == 0:
            draw.text((70, y), line, fill=fill, font=title_font)
            y += 86
            continue
        if index == 1:
            y += 12
            continue
        font = small_font if index == len(lines) - 1 else text_font
        draw.text((70, y), line, fill=fill, font=font)
        y += 70

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return BufferedInputFile(buffer.getvalue(), filename="profile_card.png")


async def get_user(tg_user_id: int) -> Optional[User]:
    async with db() as session:
        return await session.scalar(select(User).where(User.tg_user_id == tg_user_id))


async def ensure_user_exists(message: Message) -> User:
    telegram_user = message.from_user
    assert telegram_user is not None

    async with db() as session:
        user = await session.scalar(select(User).where(User.tg_user_id == telegram_user.id))
        if user is None:
            nickname = telegram_user.username or telegram_user.first_name or "Игрок"
            user = User(
                tg_user_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                nickname=nickname,
            )
            session.add(user)
        else:
            user.username = telegram_user.username
            user.first_name = telegram_user.first_name
            if not user.nickname:
                user.nickname = telegram_user.username or telegram_user.first_name or "Игрок"
        await session.commit()
        await session.refresh(user)
        return user


async def render_main_menu(chat_id: int, user: User, state: FSMContext) -> None:
    nickname = user.nickname or user.username or user.first_name or "Игрок"
    caption = (
        "Привет, {}!\n\n"
        "Добро пожаловать в Mafia Bot.\n"
        "Выбери действие в меню ниже."
    ).format(nickname)
    keyboard = main_menu_keyboard()
    photo = build_profile_image(user, nickname)
    data = await state.get_data()
    message_id = data.get("menu_message_id")

    if message_id:
        try:
            await bot.edit_message_media(
                chat_id=chat_id,
                message_id=message_id,
                media=InputMediaPhoto(media=photo, caption=caption),
                reply_markup=keyboard,
            )
            await set_menu_message_id(user.tg_user_id, message_id)
            return
        except TelegramBadRequest:
            pass
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest:
            pass

    sent = await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=keyboard)
    await state.update_data(menu_message_id=sent.message_id)
    await set_menu_message_id(user.tg_user_id, sent.message_id)


async def edit_menu_caption(chat_id: int, message_id: int, text: str, keyboard: InlineKeyboardMarkup) -> None:
    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=text,
            reply_markup=keyboard,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def rules_text() -> str:
    return (
        "Правила Мафии\n\n"
        "1. Есть две стороны: мафия и мирные.\n"
        "2. Ночью мафия делает ход, днем игроки обсуждают и голосуют.\n"
        "3. Мирные побеждают, когда выбили всю мафию.\n"
        "4. Мафия побеждает, когда сравнялась по числу с мирными.\n\n"
        "Собирай команду и начинай игру."
    )


@router.message(Command("start"), F.chat.type == "private")
async def command_start(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    menu_message_id = data.get("menu_message_id")
    await state.clear()
    if menu_message_id:
        await state.update_data(menu_message_id=menu_message_id)
    user = await ensure_user_exists(message)
    await render_main_menu(chat_id=message.chat.id, user=user, state=state)


@router.callback_query(F.data == "menu_settings")
async def callback_settings(query: CallbackQuery, state: FSMContext) -> None:
    user = await get_user(query.from_user.id)
    if user is None:
        return
    await query.answer()
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=(
            "Настройки\n\n"
            "Здесь можно включить/выключить рассылку и сменить никнейм."
        ),
        keyboard=settings_keyboard(user.notifications_enabled),
    )
    await state.update_data(menu_message_id=query.message.message_id)


@router.callback_query(F.data == "settings_toggle_notifications")
async def callback_toggle_notifications(query: CallbackQuery) -> None:
    user = await get_user(query.from_user.id)
    if user is None:
        return

    new_value = not user.notifications_enabled
    async with db() as session:
        await session.execute(
            update(User).where(User.tg_user_id == query.from_user.id).values(notifications_enabled=new_value)
        )
        await session.commit()

    await query.answer("Настройка обновлена")
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text="Настройки\n\nЗдесь можно включить/выключить рассылку и сменить никнейм.",
        keyboard=settings_keyboard(new_value),
    )


@router.callback_query(F.data == "settings_change_nickname")
async def callback_change_nickname(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.set_state(SettingsState.waiting_nickname)
    await state.update_data(menu_message_id=query.message.message_id)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=(
            "Смена никнейма\n\n"
            "Отправь новый никнейм одним сообщением.\n"
            "Длина: 2-32 символа."
        ),
        keyboard=nickname_input_keyboard(),
    )


@router.message(SettingsState.waiting_nickname)
async def handle_nickname_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    menu_message_id = data.get("menu_message_id")
    new_nickname = (message.text or "").strip()
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    if len(new_nickname) < 2 or len(new_nickname) > 32:
        if menu_message_id:
            await edit_menu_caption(
                chat_id=message.chat.id,
                message_id=menu_message_id,
                text=(
                    "Смена никнейма\n\n"
                    "Никнейм должен быть от 2 до 32 символов.\n"
                    "Отправь новый никнейм."
                ),
                keyboard=nickname_input_keyboard(),
            )
        return

    async with db() as session:
        await session.execute(
            update(User).where(User.tg_user_id == message.from_user.id).values(nickname=new_nickname)
        )
        await session.commit()

    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    await state.clear()
    if menu_message_id:
        await state.update_data(menu_message_id=menu_message_id)
    user = await get_user(message.from_user.id)
    if user is None:
        return

    await render_main_menu(chat_id=message.chat.id, user=user, state=state)


@router.callback_query(F.data == "menu_rules")
async def callback_rules(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=rules_text(),
        keyboard=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back_main")]]
        ),
    )
    await state.update_data(menu_message_id=query.message.message_id)


@router.callback_query(F.data == "menu_rating")
async def callback_rating(query: CallbackQuery, state: FSMContext) -> None:
    user = await get_user(query.from_user.id)
    if user is None:
        return
    await query.answer()
    win_rate = round((user.wins / max(user.games_played, 1)) * 100, 1)
    await edit_menu_caption(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=(
            "Рейтинг игрока\n\n"
            "Рейтинг: {}\n"
            "Игр сыграно: {}\n"
            "Победы: {} ({}%)"
        ).format(user.rating, user.games_played, user.wins, win_rate),
        keyboard=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back_main")]]
        ),
    )
    await state.update_data(menu_message_id=query.message.message_id)


@router.callback_query(F.data == "back_main")
async def callback_back_main(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.clear()
    user = await get_user(query.from_user.id)
    if user is None:
        return
    await state.update_data(menu_message_id=query.message.message_id)
    await render_main_menu(chat_id=query.message.chat.id, user=user, state=state)

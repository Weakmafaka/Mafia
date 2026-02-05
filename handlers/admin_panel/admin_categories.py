from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from utils.s3_service import get_url
from utils.library import bot

router = Router()

class AdminContent(StatesGroup):
    choosing_age = State()
    browsing_folder = State()


@router.callback_query(F.data == 'admin_category')
async def admin_category(query: CallbackQuery):
    await bot.delete_message(chat_id=query.message.chat.id,
                             message_id=query.message.message_id)
    from main import db
    if not db.is_admin(query.from_user.id):
        return

    age_buttons = [
        [
            InlineKeyboardButton(text="0-3 года 👶", callback_data="admin_age_0-3"),
            InlineKeyboardButton(text="4-6 лет 🧒", callback_data="admin_age_4-6")
        ],
        [InlineKeyboardButton(text="7-10 лет 👦", callback_data="admin_age_7-10")],
        [
            InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="admin_panel")
        ]
    ]
    age_keyboard = InlineKeyboardMarkup(inline_keyboard=age_buttons)

    await bot.send_message(
        chat_id=query.message.chat.id,
        text="Выберите возраст для управления доступом к категориям:",
        reply_markup=age_keyboard
    )


@router.callback_query(F.data.startswith("admin_age_"))
async def admin_age(query: CallbackQuery, state: FSMContext):
    age_group = query.data.split('_')[2]

    # Начальные данные
    base_path = f"/Контент/{age_group}/Полезное"
    await state.set_state(AdminContent.browsing_folder)
    await state.update_data(
        age_group=age_group,
        current_path=base_path,
        path_stack=[base_path]
    )

    await bot.delete_message(query.message.chat.id, query.message.message_id)
    await show_folder_contents(query, state)


@router.callback_query(F.data == "admin_nav_back")
async def admin_nav_back(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    path_stack = data.get("path_stack", [])

    if len(path_stack) <= 1:
        await state.set_state(AdminContent.choosing_age)
        await query.message.answer("Выберите возраст")
        return

    path_stack.pop()
    await state.update_data(path_stack=path_stack, current_path=path_stack[-1])
    await bot.delete_message(query.message.chat.id, query.message.message_id)
    await show_folder_contents(query, state)


@router.callback_query(F.data.startswith("admin_folder_"))
async def admin_open_folder(query: CallbackQuery, state: FSMContext):
    folder_name = query.data.split("_", 2)[2]
    data = await state.get_data()
    current_path = data["current_path"]
    new_path = f"{current_path}/{folder_name}"

    # Обновим путь
    path_stack = data.get("path_stack", [])
    path_stack.append(new_path)
    await state.update_data(current_path=new_path, path_stack=path_stack)

    await bot.delete_message(query.message.chat.id, query.message.message_id)
    await show_folder_contents(query, state)


async def show_folder_contents(query: CallbackQuery, state: FSMContext):
    from main import db
    data = await state.get_data()
    path = data["current_path"]
    age_group = data["age_group"]

    items = await get_url(path)

    subfolders = [item for item in items if item.type == 'dir']
    files = [item for item in items if item.type == 'file']
    locked = db.get_all_locked_categories()
    folder_name = path.split("/")[-1]

    # === 🧠 Авторазблокировка родителя, если есть хотя бы одна открыт. подпапка ===
    unlocked_subfolder_exists = any(folder.name not in locked for folder in subfolders)
    if unlocked_subfolder_exists and folder_name in locked:
        db.remove_locked_category(folder_name)
        locked.remove(folder_name)

    buttons = []

    # === Подпапки ===
    # === Подпапки с корректной иконкой (по содержимому) ===
    for folder in subfolders:
        folder_path = f"{path}/{folder.name}"
        subitems = await get_url(folder_path)
        sub_subfolders = [item for item in subitems if item.type == 'dir']

        # Проверка: все ли подпапки внутри этой папки заблокированы
        if sub_subfolders:
            all_sub_locked = all(sub.name in locked for sub in sub_subfolders)
            icon = "❌" if all_sub_locked else "✅"
        else:
            # Если подпапок нет — ориентируемся на саму папку
            icon = "❌" if folder.name in locked else "✅"

        buttons.append([InlineKeyboardButton(
            text=f"{folder.name} {icon}",
            callback_data=f"admin_folder_{folder.name}"
        )])

    # === 🔁 Кнопка "Заблокировать все / Разблокировать все"
    if subfolders and path != f"/Контент/{age_group}/Полезное":
        all_locked = all(folder.name in locked for folder in subfolders)
        if all_locked:
            btn_text = "✅ Разблокировать все"
            btn_data = "unlock_all"
        else:
            btn_text = "❌ Заблокировать все"
            btn_data = "lock_all"

        buttons.append([
            InlineKeyboardButton(text=btn_text, callback_data=btn_data)
        ])

    # === Кнопка блокировки текущей папки ===
    if files or not items:  # ← разрешаем блокировку даже если папка пуста
        if folder_name in locked:
            lock_btn = InlineKeyboardButton(
                text="✅ Разблокировать эту папку",
                callback_data=f"toggle_lock_{folder_name}"
            )
        else:
            lock_btn = InlineKeyboardButton(
                text="❌ Заблокировать эту папку",
                callback_data=f"toggle_lock_{folder_name}"
            )
        buttons.append([lock_btn])

    # === Навигация ===
    nav_row = []
    if path != f"/Контент/{age_group}/Полезное":
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_nav_back"))
    nav_row.append(InlineKeyboardButton(text="🏠 Меню", callback_data="admin_panel"))
    buttons.append(nav_row)

    await bot.send_message(
        query.message.chat.id,
        f"📂 <b>{folder_name}</b>\n\n✅ — открыт, ❌ — под подпиской",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("toggle_lock_"))
async def toggle_lock(query: CallbackQuery, state: FSMContext):
    from main import db
    folder_name = query.data.split("_", 2)[2]

    if db.is_category_locked(folder_name):
        db.remove_locked_category(folder_name)
    else:
        db.add_locked_category(folder_name)

    await bot.delete_message(query.message.chat.id, query.message.message_id)
    await show_folder_contents(query, state)


@router.callback_query(F.data.in_(["lock_all", "unlock_all"]))
async def toggle_all_subfolders(query: CallbackQuery, state: FSMContext):
    from main import db
    data = await state.get_data()
    path = data["current_path"]
    items = await get_url(path)
    subfolders = [item for item in items if item.type == 'dir']

    if query.data == "lock_all":
        for folder in subfolders:
            if not db.is_category_locked(folder.name):
                db.add_locked_category(folder.name)
    else:  # unlock_all
        for folder in subfolders:
            if db.is_category_locked(folder.name):
                db.remove_locked_category(folder.name)

    await bot.delete_message(query.message.chat.id, query.message.message_id)
    await show_folder_contents(query, state)

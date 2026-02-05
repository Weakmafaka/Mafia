from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from utils.library import bot
from datetime import datetime, timedelta
from collections import Counter

router = Router()

def format_percent(value: float) -> str:
    """Форматирует процент с одним знаком после запятой"""
    return f"{value:.1f}%"

def get_activity_stats(users: list) -> dict:
    """Анализирует активность пользователей"""
    now = datetime.now()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    
    active_24h = 0
    active_week = 0
    days_activity = Counter()
    hours_activity = Counter()
    
    for user in users:
        if 'last_activity' in user:
            last_active = datetime.strptime(user['last_activity'], "%Y-%m-%d %H:%M:%S")
            
            if last_active >= day_ago:
                active_24h += 1
                hours_activity[last_active.hour] += 1
            
            if last_active >= week_ago:
                active_week += 1
                days_activity[last_active.strftime("%A")] += 1
    
    peak_hour = max(hours_activity.items(), key=lambda x: x[1])[0] if hours_activity else 0
    most_active_day = max(days_activity.items(), key=lambda x: x[1])[0] if days_activity else "N/A"
    
    return {
        "active_24h": active_24h,
        "active_week": active_week,
        "peak_hour": peak_hour,
        "most_active_day": most_active_day
    }

def get_retention_stats(users: list) -> dict:
    """Анализирует удержание пользователей"""
    now = datetime.now()
    total_users = len(users)
    if not total_users:
        return {"retention": 0, "avg_usage_days": 0}
    
    retained_users = 0
    total_usage_days = 0
    
    for user in users:
        reg_date = datetime.strptime(user['registration_date'], "%Y-%m-%d %H:%M:%S")
        if 'last_activity' in user:
            last_active = datetime.strptime(user['last_activity'], "%Y-%m-%d %H:%M:%S")
            days_since_reg = (now - reg_date).days
            
            if days_since_reg >= 1 and last_active > reg_date + timedelta(days=1):
                retained_users += 1
            
            usage_days = (last_active - reg_date).days + 1
            total_usage_days += usage_days
    
    return {
        "retention": (retained_users / total_users * 100),
        "avg_usage_days": total_usage_days / total_users
    }

async def get_statistics_message(db) -> str:
    """Формирует сообщение со статистикой"""
    users = db.get_all_users()
    total_users = len(users)
    
    # Базовая статистика
    premium_users = sum(1 for user in users if user['is_premium'])
    premium_percent = (premium_users / total_users * 100) if total_users > 0 else 0
    
    # Статистика за периоды
    week_ago = datetime.now() - timedelta(days=7)
    month_ago = datetime.now() - timedelta(days=30)
    
    new_users_week = []
    new_users_month = []
    new_premium_week = 0
    new_premium_month = 0
    
    for user in users:
        reg_date = datetime.strptime(user['registration_date'], "%Y-%m-%d %H:%M:%S")
        
        if reg_date >= week_ago:
            new_users_week.append(user)
            if user['is_premium']:
                new_premium_week += 1
                
        if reg_date >= month_ago:
            new_users_month.append(user)
            if user['is_premium']:
                new_premium_month += 1
    
    # Возрастные группы
    age_stats = db.get_age_selection_stats()
    total_age_selections = sum(age_stats.values()) or 1
    
    # Получаем дополнительную статистику
    activity_stats = get_activity_stats(users)
    retention_stats = get_retention_stats(users)
    
    # Формируем сообщение
    message = (
        "📊 <b>ОБЩАЯ СТАТИСТИКА</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"⭐ С подпиской: {premium_users} ({format_percent(premium_percent)})\n"
        f"♻️ Удержание после 1 дня: {format_percent(retention_stats['retention'])}\n"
        f"📅 Среднее время использования: {retention_stats['avg_usage_days']:.1f} дней\n\n"
        
        "👶 <b>ВОЗРАСТНЫЕ ГРУППЫ</b>\n"
        f"0-3 года: {age_stats.get('0-3', 0)} ({format_percent(age_stats.get('0-3', 0) / total_age_selections * 100)})\n"
        f"4-6 лет: {age_stats.get('4-6', 0)} ({format_percent(age_stats.get('4-6', 0) / total_age_selections * 100)})\n"
        f"7-10 лет: {age_stats.get('7-10', 0)} ({format_percent(age_stats.get('7-10', 0) / total_age_selections * 100)})\n\n"
        
        "📱 <b>АКТИВНОСТЬ</b>\n"
        f"За 24 часа: {activity_stats['active_24h']} ({format_percent(activity_stats['active_24h'] / total_users * 100)})\n"
        f"За неделю: {activity_stats['active_week']} ({format_percent(activity_stats['active_week'] / total_users * 100)})\n"
        f"Пиковое время: {activity_stats['peak_hour']}:00\n"
        f"Самый активный день: {activity_stats['most_active_day']}\n\n"
        
        "📈 <b>ДИНАМИКА</b>\n"
        f"🆕 Новых за неделю: {len(new_users_week)}\n"
        f"💰 Подписок за неделю: {new_premium_week} ({format_percent(new_premium_week / len(new_users_week) * 100 if new_users_week else 0)})\n"
        f"🆕 Новых за месяц: {len(new_users_month)}\n"
        f"💰 Подписок за месяц: {new_premium_month} ({format_percent(new_premium_month / len(new_users_month) * 100 if new_users_month else 0)})\n"
    )
    
    return message

@router.callback_query(F.data == 'admin_stat')
async def admin_stat(query: CallbackQuery):
    await bot.delete_message(chat_id=query.message.chat.id,
                           message_id=query.message.message_id)
    from main import db
    is_admin = db.is_admin(query.from_user.id)
    if is_admin:
        menu_buttons = [
            [
                InlineKeyboardButton(text="Вернуться назад ⏪", callback_data="admin_panel")
            ]
        ]
        menu = InlineKeyboardMarkup(inline_keyboard=menu_buttons)
        stat_message = await get_statistics_message(db)
        await bot.send_message(chat_id=query.message.chat.id,
                             text=stat_message,
                             parse_mode="HTML",
                             reply_markup=menu)
    else:
        return
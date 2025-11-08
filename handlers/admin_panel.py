# ============================================
# FILE: handlers/admin_panel.py (ПОЛНАЯ ВЕРСИЯ)
# ============================================

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from datetime import datetime, timezone
import logging

from config import TIMEZONE
from database.db_manager import get_db
from database.models import get_user_profile
from utils.keyboards import get_admin_keyboard, get_export_keyboard, get_main_keyboard
from utils.decorators import admin_only, admin_callback_only

logger = logging.getLogger(__name__)


def get_local_time():
    """Получить текущее локальное время"""
    return datetime.now(TIMEZONE)


@admin_only
async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать админ-панель"""
    text = """
🔧 **Административная панель**

Добро пожаловать в панель управления Campus Check-in Bot!

Выберите действие:
    """
    
    await update.message.reply_text(
        text,
        reply_markup=get_admin_keyboard()
    )


@admin_callback_only
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback админ-панели"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'admin_monitoring':
        await show_monitoring(query, context)
    
    elif query.data == 'admin_events_archive':
        await show_events_archive(query, context)
    
    elif query.data == 'admin_export_data':
        await show_export_menu(query, context)
    
    elif query.data == 'admin_panel':
        text = """
🔧 **Административная панель**

Выберите действие:
        """
        await query.edit_message_text(
            text,
            reply_markup=get_admin_keyboard()
        )
    
    elif query.data == 'admin_close':
        await query.message.delete()


async def show_monitoring(query, context):
    """Мониторинг присутствия"""
    today = get_local_time().date()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                u.user_id,
                u.first_name,
                u.last_name,
                u.username,
                u.team_role,
                u.phone_number,
                p.check_in_time,
                p.latitude,
                p.longitude
            FROM presence p
            JOIN users u ON p.user_id = u.user_id
            WHERE p.date = %s AND p.status = 'in_campus'
            ORDER BY p.check_in_time DESC
        ''', (today,))
        
        active_users = cursor.fetchall()
    
    if not active_users:
        text = "📊 **Мониторинг присутствия**\n\nСейчас никого нет в кампусе."
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    text = f"📊 **Мониторинг присутствия**\n\n"
    text += f"Активных пользователей: {len(active_users)}\n\n"
    
    keyboard = []
    
    for user in active_users:
        check_in = user['check_in_time']
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=timezone.utc)
        local_time = check_in.astimezone(TIMEZONE)
        
        name = f"{user['first_name']} {user['last_name']}"
        team = user['team_role'] if user['team_role'] else "Не указано"
        
        text += f"🟢 {name}\n"
        text += f"   └ {team} • С {local_time.strftime('%H:%M')}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"👤 {name}",
                callback_data=f"admin_profile_{user['user_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    await query.edit_message_text(
        text[:4000],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_events_archive(query, context):
    """Архив мероприятий"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, start_time, end_time
            FROM events
            WHERE end_time < CURRENT_TIMESTAMP
            ORDER BY start_time DESC
            LIMIT 20
        ''')
        
        events = cursor.fetchall()
    
    if not events:
        text = "📋 **Архив мероприятий**\n\nПока нет завершенных мероприятий."
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    text = "📋 **Архив мероприятий**\n\nВыберите мероприятие для просмотра:\n\n"
    
    keyboard = []
    for event in events:
        start = event['start_time']
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        local_start = start.astimezone(TIMEZONE)
        
        btn_text = f"{event['name']} ({local_start.strftime('%d.%m.%Y')})"
        keyboard.append([
            InlineKeyboardButton(
                btn_text,
                callback_data=f"admin_event_{event['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_export_menu(query, context):
    """Меню экспорта данных"""
    text = """
📊 **Экспорт данных**

Выберите период для выгрузки данных о присутствии:
    """
    
    await query.edit_message_text(
        text,
        reply_markup=get_export_keyboard()
    )


async def handle_profile_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр профиля пользователя админом"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith('admin_profile_'):
        return
    
    user_id = int(query.data.replace('admin_profile_', ''))
    
    profile = get_user_profile(user_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT check_in_time, check_out_time, latitude, longitude
            FROM presence
            WHERE user_id = %s
            ORDER BY check_in_time DESC
            LIMIT 1
        ''', (user_id,))
        last_presence = cursor.fetchone()
    
    text = f"""
👤 **Профиль участника**

**Личные данные:**
• ФИО: {profile['first_name']} {profile['last_name']}
• Username: @{profile['username']}
• Телефон: {profile['phone_number']}
• Дата рождения: {profile['birth_date'].strftime('%d.%m.%Y')}
• Команда/Роль: {profile['team_role']}

**Статистика:**
• Ранг: {profile['current_rank']}
• Всего отметок: {profile['total_checkins']}
• Геолокация: {'✅ Включена' if profile['geo_consent'] else '❌ Отключена'}
    """
    
    keyboard = []
    
    if last_presence and last_presence['latitude']:
        lat = last_presence['latitude']
        lon = last_presence['longitude']
        maps_url = f"https://www.google.com/maps?q={lat},{lon}"
        
        keyboard.append([
            InlineKeyboardButton("🗺 Показать на карте", url=maps_url)
        ])
        
        check_in = last_presence['check_in_time']
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=timezone.utc)
        local_time = check_in.astimezone(TIMEZONE)
        
        text += f"\n**Последнее присутствие:**\n"
        text += f"🕐 {local_time.strftime('%d.%m.%Y %H:%M')}\n"
    
    keyboard.append([InlineKeyboardButton("◀️ К мониторингу", callback_data="admin_monitoring")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_event_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать детали мероприятия"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith('admin_event_'):
        return
    
    event_id = int(query.data.replace('admin_event_', ''))
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT name, start_time, end_time, description
            FROM events
            WHERE id = %s
        ''', (event_id,))
        event = cursor.fetchone()
        
        cursor.execute('''
            SELECT 
                u.first_name,
                u.last_name,
                u.team_role,
                p.check_in_time,
                p.check_out_time
            FROM presence p
            JOIN users u ON p.user_id = u.user_id
            WHERE p.event_id = %s
            ORDER BY p.check_in_time
        ''', (event_id,))
        participants = cursor.fetchall()
    
    start = event['start_time']
    end = event['end_time']
    
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    
    local_start = start.astimezone(TIMEZONE)
    local_end = end.astimezone(TIMEZONE)
    
    text = f"""
🎯 **{event['name']}**

📅 Начало: {local_start.strftime('%d.%m.%Y %H:%M')}
📅 Окончание: {local_end.strftime('%d.%m.%Y %H:%M')}

{event['description'] if event['description'] else ''}

👥 **Участники ({len(participants)} чел.):**

    """
    
    for p in participants:
        name = f"{p['first_name']} {p['last_name']}"
        team = p['team_role'] if p['team_role'] else "Не указано"
        
        check_in = p['check_in_time']
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=timezone.utc)
        local_check_in = check_in.astimezone(TIMEZONE)
        
        text += f"• {name} ({team})\n"
        text += f"  └ {local_check_in.strftime('%H:%M')}"
        
        if p['check_out_time']:
            check_out = p['check_out_time']
            if check_out.tzinfo is None:
                check_out = check_out.replace(tzinfo=timezone.utc)
            local_check_out = check_out.astimezone(TIMEZONE)
            text += f" - {local_check_out.strftime('%H:%M')}"
        
        text += "\n\n"
    
    keyboard = [
        [InlineKeyboardButton(f"📊 Экспорт", callback_data=f"export_event_{event_id}")],
        [InlineKeyboardButton("◀️ К архиву", callback_data="admin_events_archive")]
    ]
    
    await query.edit_message_text(
        text[:4000],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

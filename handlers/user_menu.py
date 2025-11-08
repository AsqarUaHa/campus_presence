# ============================================
# FILE: handlers/user_menu.py
# ============================================

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from datetime import datetime, timezone, timedelta
import logging

from config import TIMEZONE
from database.db_manager import get_db
from database.models import get_user_profile, get_all_users_status
from utils.keyboards import get_main_keyboard, get_settings_keyboard
from utils.decorators import registered_only
from utils.geo_utils import get_status_indicator

logger = logging.getLogger(__name__)


def get_local_time():
    """Получить текущее локальное время"""
    return datetime.now(TIMEZONE)


@registered_only
async def show_my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус пользователя"""
    user_id = update.effective_user.id
    today = get_local_time().date()
    
    profile = get_user_profile(user_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Статус присутствия сегодня
        cursor.execute('''
            SELECT check_in_time, check_out_time, status
            FROM presence
            WHERE user_id = %s AND date = %s
            ORDER BY check_in_time DESC LIMIT 1
        ''', (user_id, today))
        presence = cursor.fetchone()
        
        # Последняя геолокация
        cursor.execute('''
            SELECT distance_to_campus, is_near_campus, timestamp
            FROM geolocation
            WHERE user_id = %s
            ORDER BY timestamp DESC LIMIT 1
        ''', (user_id,))
        geo = cursor.fetchone()
        
        # Получаем emoji ранга
        cursor.execute('SELECT emoji FROM ranks WHERE name = %s', (profile['current_rank'],))
        rank_emoji = cursor.fetchone()['emoji']
    
    text = f"""
📊 **Ваш профиль**

👤 Имя: {profile['first_name']} {profile['last_name']}
👥 Команда/Роль: {profile['team_role']}
{rank_emoji} Ранг: **{profile['current_rank']}**
📈 Всего отметок: {profile['total_checkins']}

**Статус сегодня:**
"""
    
    if presence:
        if presence['status'] == 'in_campus':
            check_in = presence['check_in_time']
            if check_in.tzinfo is None:
                check_in = check_in.replace(tzinfo=timezone.utc)
            local_time = check_in.astimezone(TIMEZONE)
            text += f"🟢 В кампусе с {local_time.strftime('%H:%M')}\n"
        else:
            text += f"⚪ Вне кампуса\n"
    else:
        text += f"⚪ Сегодня не отмечались\n"
    
    text += f"\n📍 Геолокация: {'✅ Включена' if profile['geo_consent'] else '❌ Отключена'}\n"
    
    if geo and profile['geo_consent']:
        distance = int(geo['distance_to_campus'])
        is_near = geo['is_near_campus']
        last_update = geo['timestamp']
        
        if last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=timezone.utc)
        local_update = last_update.astimezone(TIMEZONE)
        
        if is_near:
            text += f"🟡 Рядом с кампусом ({distance}м)\n"
        else:
            text += f"📍 Расстояние: {distance}м\n"
        
        text += f"🕐 Обновлено: {local_update.strftime('%H:%M')}\n"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())


@registered_only
async def show_who_inside(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список присутствующих в кампусе"""
    today = get_local_time().date()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                u.first_name,
                u.last_name,
                u.username,
                u.team_role,
                u.current_rank,
                p.check_in_time,
                g.is_near_campus,
                g.distance_to_campus
            FROM presence p
            JOIN users u ON p.user_id = u.user_id
            LEFT JOIN (
                SELECT DISTINCT ON (user_id) user_id, is_near_campus, distance_to_campus
                FROM geolocation
                ORDER BY user_id, timestamp DESC
            ) g ON u.user_id = g.user_id
            WHERE p.date = %s AND p.status = 'in_campus'
            ORDER BY p.check_in_time
        ''', (today,))
        
        people = cursor.fetchall()
    
    if not people:
        await update.message.reply_text(
            "😔 Сейчас никого нет в кампусе.",
            reply_markup=get_main_keyboard()
        )
        return
    
    text = f"👥 **В кампусе сейчас: {len(people)} чел.**\n\n"
    
    for person in people:
        check_in = person['check_in_time']
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=timezone.utc)
        local_time = check_in.astimezone(TIMEZONE)
        
        status_icon = "🟢"
        status_text = ""
        
        if person['is_near_campus'] is not None and person['distance_to_campus']:
            if person['is_near_campus']:
                status_icon = "🟡"
                status_text = f" - Рядом ({int(person['distance_to_campus'])}м)"
        
        name = f"{person['first_name']} {person['last_name']}"
        team = f" ({person['team_role']})" if person['team_role'] else ""
        username = f"@{person['username']}" if person['username'] else ""
        
        text += f"{status_icon} {name}{team}{status_text}\n"
        text += f"   └ {username} • С {local_time.strftime('%H:%M')}\n\n"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())


@registered_only
async def show_all_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать всех участников с индикаторами статуса"""
    users = get_all_users_status()
    
    if not users:
        await update.message.reply_text(
            "📝 Пока нет зарегистрированных участников.",
            reply_markup=get_main_keyboard()
        )
        return
    
    text = f"👤 **Все участники ({len(users)} чел.):**\n\n"
    
    for user in users:
        # Определяем индикатор статуса
        emoji, status_text = get_status_indicator(
            user['presence_status'],
            user['is_near_campus'],
            user['last_geo_update']
        )
        
        name = f"{user['first_name']} {user['last_name']}"
        team = user['team_role'] if user['team_role'] else "Не указано"
        username = f"@{user['username']}" if user['username'] else ""
        
        text += f"{emoji} {name}\n"
        text += f"   └ {team} • {username}\n\n"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())


@registered_only
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать настройки"""
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    text = f"""
⚙️ **Настройки**

👤 **Профиль:**
• Имя: {profile['first_name']} {profile['last_name']}
• Команда/Роль: {profile['team_role']}
• Телефон: {profile['phone_number']}
• Дата рождения: {profile['birth_date'].strftime('%d.%m.%Y')}

📊 **Статистика:**
• Ранг: {profile['current_rank']}
• Всего отметок: {profile['total_checkins']}

📍 **Геолокация:** {'✅ Включена' if profile['geo_consent'] else '❌ Отключена'}
    """
    
    await update.message.reply_text(
        text,
        reply_markup=get_settings_keyboard(profile['geo_consent'])
    )


async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback настроек"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'toggle_geo':
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT geo_consent FROM users WHERE user_id = %s', (user_id,))
            current = cursor.fetchone()['geo_consent']
            new_value = not current
            
            cursor.execute(
                'UPDATE users SET geo_consent = %s WHERE user_id = %s',
                (new_value, user_id)
            )
            conn.commit()
        
        profile = get_user_profile(user_id)
        
        text = f"""
⚙️ **Настройки**

👤 **Профиль:**
• Имя: {profile['first_name']} {profile['last_name']}
• Команда/Роль: {profile['team_role']}
• Телефон: {profile['phone_number']}
• Дата рождения: {profile['birth_date'].strftime('%d.%m.%Y')}

📊 **Статистика:**
• Ранг: {profile['current_rank']}
• Всего отметок: {profile['total_checkins']}

📍 **Геолокация:** {'✅ Включена' if new_value else '❌ Отключена'}
        """
        
        await query.edit_message_text(
            text,
            reply_markup=get_settings_keyboard(new_value)
        )
        
        status = "включена ✅" if new_value else "отключена ❌"
        await query.message.reply_text(f"Геолокация {status}")
    
    elif query.data == 'edit_profile':
        await query.message.reply_text(
            "✏️ **Редактирование профиля**\n\n"
            "Для изменения данных обратитесь к администратору.",
            reply_markup=get_main_keyboard()
        )
    
    elif query.data == 'my_stats':
        # Расширенная статистика
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Всего дней присутствия
            cursor.execute('''
                SELECT COUNT(DISTINCT date) as total_days
                FROM presence
                WHERE user_id = %s AND status = 'in_campus'
            ''', (user_id,))
            total_days = cursor.fetchone()['total_days']
            
            # Среднее время пребывания
            cursor.execute('''
                SELECT AVG(EXTRACT(EPOCH FROM (check_out_time - check_in_time))/3600) as avg_hours
                FROM presence
                WHERE user_id = %s AND check_out_time IS NOT NULL
            ''', (user_id,))
            avg_hours = cursor.fetchone()['avg_hours']
            avg_hours = round(avg_hours, 1) if avg_hours else 0
            
            # След. ранг
            profile = get_user_profile(user_id)
            cursor.execute('''
                SELECT name, min_checkins
                FROM ranks
                WHERE min_checkins > %s
                ORDER BY min_checkins
                LIMIT 1
            ''', (profile['total_checkins'],))
            next_rank = cursor.fetchone()
        
        stats_text = f"""
📊 **Расширенная статистика**

📈 Всего отметок: {profile['total_checkins']}
📅 Дней присутствия: {total_days}
⏱ Среднее время: {avg_hours} ч
        """
        
        if next_rank:
            needed = next_rank['min_checkins'] - profile['total_checkins']
            stats_text += f"\n🎯 До ранга '{next_rank['name']}': {needed} отметок"
        else:
            stats_text += f"\n🏆 Вы достигли максимального ранга!"
        
        await query.message.reply_text(stats_text, reply_markup=get_main_keyboard())
    
    elif query.data == 'settings_close':
        await query.message.delete()


@registered_only
async def show_knowledge_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать базу знаний"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, title, file_type
            FROM knowledge_base
            ORDER BY upload_time DESC
        ''')
        files = cursor.fetchall()
    
    if not files:
        await update.message.reply_text(
            "📚 База знаний пока пуста.",
            reply_markup=get_main_keyboard()
        )
        return
    
    keyboard = []
    for file in files:
        file_icon = "📄" if file['file_type'] == 'document' else "📎"
        keyboard.append([
            InlineKeyboardButton(
                f"{file_icon} {file['title']}",
                callback_data=f"kb_file_{file['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="kb_close")])
    
    await update.message.reply_text(
        "📚 **База знаний**\n\nВыберите материал:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_knowledge_base_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback базы знаний"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('kb_file_'):
        file_id_str = query.data.replace('kb_file_', '')
        file_id = int(file_id_str)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT file_id, title, file_type
                FROM knowledge_base
                WHERE id = %s
            ''', (file_id,))
            file = cursor.fetchone()
        
        if file:
            await query.message.reply_document(
                document=file['file_id'],
                caption=f"📚 {file['title']}"
            )
    
    elif query.data == 'kb_close':
        await query.message.delete()

# ============================================
# FILE: handlers/admin_panel.py (ПОЛНАЯ ВЕРСИЯ)
# ============================================

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from datetime import datetime, timezone
import logging

from config import TIMEZONE, States
from database.db_manager import get_db
from database.models import get_user_profile
from utils.keyboards import get_admin_keyboard, get_export_keyboard, get_main_keyboard
from utils.decorators import admin_only, admin_callback_only
from features.posts_scheduler import create_post
from features.knowledge_base import upload_to_kb
from handlers.contests import start_photo_contest, view_contest_photos, end_photo_contest

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
    data = query.data
    
    if data == 'admin_monitoring':
        await show_monitoring(query, context)
    
    elif data == 'admin_all_users':
        await show_all_registered_users(query)
    
    elif data == 'admin_events_archive':
        await show_events_archive(query, context)
    
    elif data == 'admin_export_data':
        await show_export_menu(query, context)
    
    elif data == 'admin_photo_contest':
        await show_photo_contest_menu(query)
        
    elif data == 'admin_contest_view':
        await view_contest_photos(update, context)
        
    elif data == 'admin_contest_end':
        # Завершение конкурса вручную
        await end_photo_contest(context)
        try:
            await query.message.reply_text("🏁 Конкурс завершён. Итоги отправлены участникам (если были фото).")
        except Exception:
            pass
            
     elif data == 'admin_contest_delete':
        from handlers.contests import admin_contest_delete
        await admin_contest_delete(update, context)
    
    elif data == 'admin_panel':
        text = """
🔧 **Административная панель**

Выберите действие:
        """
        await query.edit_message_text(
            text,
            reply_markup=get_admin_keyboard()
        )
    
    elif data == 'admin_close':
        await query.message.delete()
    elif data == 'admin_close':
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


async def show_photo_contest_menu(query):
    """Подменю конкурса фото"""
    # Проверим, есть ли активный конкурс на сегодня
    end_info = None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT end_time, is_closed FROM photo_contest_schedule
            WHERE contest_date = CURRENT_DATE
        ''')
        end_info = cursor.fetchone()
    keyboard = [
        [InlineKeyboardButton("🚀 Запустить конкурс", callback_data='admin_contest_start')],
        [InlineKeyboardButton("🖼 Посмотреть фото", callback_data='admin_contest_view')],
        [InlineKeyboardButton("🏁 Завершить конкурс", callback_data='admin_contest_end')],
    ]
    if end_info and not end_info.get('is_closed'):
        keyboard.insert(1, [InlineKeyboardButton("⏱ Изменить время окончания", callback_data='admin_contest_edit_time')])
        keyboard.insert(2, [InlineKeyboardButton("🗑 Удалить конкурс", callback_data='admin_contest_delete')])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')])
    text = "📸 Конкурс фото — выберите действие:"
    if end_info and end_info.get('end_time'):
        from datetime import timezone as dt_tz
        end_ts = end_info['end_time']
        if end_ts and end_ts.tzinfo is None:
            end_ts = end_ts.replace(tzinfo=dt_tz.utc)
        text += f"\n\nТекущее время окончания приёма: {end_ts.astimezone(TIMEZONE).strftime('%d.%m.%Y %H:%M')}"
    await query.edit_message_text(
        text,
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


# ===============================
# Список всех зарегистрированных пользователей (с координатами)
# ===============================
async def show_all_registered_users(query):
    """Показать всех зарегистрированных пользователей с ключевой информацией и координатами."""
    from database.db_manager import get_db
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
                u.birth_date,
                u.current_rank,
                u.total_checkins,
                u.geo_consent,
                g.latitude,
                g.longitude,
                g.timestamp as geo_ts
            FROM users u
            LEFT JOIN (
                SELECT DISTINCT ON (user_id) user_id, latitude, longitude, timestamp
                FROM geolocation
                ORDER BY user_id, timestamp DESC
            ) g ON u.user_id = g.user_id
            WHERE u.is_registered = TRUE
            ORDER BY u.first_name, u.last_name
        ''')
        rows = cursor.fetchall()
    if not rows:
        await query.edit_message_text(
            "📝 Зарегистрированных пользователей пока нет.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]])
        )
        return
    text = f"👤 **Все зарегистрированные ({len(rows)} чел.)**\n\n"
    from config import TIMEZONE
    from datetime import timezone as dt_tz
    # Формируем список (усечём по лимиту Telegram 4096 символов)
    for row in rows:
        name = f"{row['first_name']} {row['last_name']}".strip()
        username = f"@{row['username']}" if row['username'] else ''
        team = row['team_role'] or 'Не указано'
        rank = row['current_rank']
        total = row['total_checkins']
        phone = row['phone_number'] or '-'
        text += f"• {name} {username}\n"
        text += f"  └ {team} • {rank} • {total} отметок\n"
        text += f"  📱 {phone}\n"
        if row['geo_consent'] and row['latitude'] is not None and row['longitude'] is not None:
            ts = row['geo_ts']
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt_tz.utc)
            ts_local = ts.astimezone(TIMEZONE) if ts else None
            lat = round(float(row['latitude']), 6)
            lon = round(float(row['longitude']), 6)
            text += f"  📍 {lat}, {lon}"
            if ts_local:
                text += f" • {ts_local.strftime('%d.%m %H:%M')}"
            text += "\n"
        else:
            text += "  📍 —\n"
        text += "\n"
    kb = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]]
    await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(kb))

# ===============================
# Админ-флоу: Создать пост
# ===============================
from telegram.ext import ConversationHandler
from datetime import datetime

async def admin_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['admin_post'] = {'media_id': None, 'event_id': None}
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data='admin_cancel')]])
    await query.edit_message_text(
        "📢 Создание поста\n\nВведите текст поста:",
        reply_markup=cancel_kb
    )
    return States.ADMIN_POST_TEXT

async def admin_post_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() in ('отмена', 'cancel'):
        return await admin_cancel_conv(update, context)
    if len(text) < 3:
        await update.message.reply_text("❌ Текст слишком короткий. Введите текст поста:")
        return States.ADMIN_POST_TEXT
    context.user_data['admin_post']['text'] = text
    await update.message.reply_text(
        "📎 Прикрепите фото к посту (необязательно).\n"
        "Отправьте фото или напишите 'пропустить'.")
    return States.ADMIN_POST_MEDIA

async def admin_post_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Фото или пропуск/отмена
    if update.message.photo:
        media_id = update.message.photo[-1].file_id
        context.user_data['admin_post']['media_id'] = media_id
    else:
        text = (update.message.text or '').strip().lower()
        if text in ('отмена', 'cancel'):
            return await admin_cancel_conv(update, context)
        if text not in ('пропустить', 'skip', 'нет', 'без фото'):
            await update.message.reply_text("Отправьте фото или напишите 'пропустить'.")
            return States.ADMIN_POST_MEDIA
    await update.message.reply_text(
        "🕐 Укажите дату и время публикации в формате ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Или напишите 'сейчас' для немедленной отправки.")
    return States.ADMIN_POST_DATETIME


def _parse_dt(text: str, tz) -> datetime | None:
    text = text.strip().lower()
    from datetime import datetime
    if text in ('сейчас', 'now', 'немедленно', 'immediately'):
        return datetime.now(tz)
    for fmt in ('%d.%m.%Y %H:%M', '%d.%m.%y %H:%M', '%d.%m %H:%M'):
        try:
            today_year = datetime.now(tz).year
            if fmt == '%d.%m %H:%M' and len(text.split()) == 2:
                dt = datetime.strptime(text, '%d.%m %H:%M')
                return dt.replace(year=today_year, tzinfo=tz)
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=tz)
        except Exception:
            continue
    return None

async def admin_post_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import TIMEZONE
    text = update.message.text
    if (text or '').strip().lower() in ('отмена', 'cancel'):
        return await admin_cancel_conv(update, context)
    dt = _parse_dt(text, TIMEZONE)
    if not dt:
        await update.message.reply_text(
            "❌ Неверный формат. Введите ДД.ММ.ГГГГ ЧЧ:ММ или 'сейчас':")
        return States.ADMIN_POST_DATETIME
    data = context.user_data['admin_post']
    post_id = await create_post(
        user_id=update.effective_user.id,
        text=data['text'],
        media_id=data['media_id'],
        scheduled_time=dt,
        event_id=data.get('event_id')
    )
    await update.message.reply_text(
        f"✅ Пост создан (ID: {post_id}).\n"
        f"🕐 Запланировано на: {dt.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=get_main_keyboard(is_admin=True)
    )
    context.user_data.pop('admin_post', None)
    return ConversationHandler.END


# ===============================
# Админ-флоу: Создать мероприятие
# ===============================
async def admin_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['admin_event'] = {}
    await query.edit_message_text("🎯 Создание мероприятия\n\nВведите название:")
    return States.ADMIN_EVENT_NAME

async def admin_event_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("❌ Название слишком короткое. Введите снова:")
        return States.ADMIN_EVENT_NAME
    context.user_data['admin_event']['name'] = name
    await update.message.reply_text("🕐 Введите дату и время начала (ДД.ММ.ГГГГ ЧЧ:ММ):")
    return States.ADMIN_EVENT_START

async def admin_event_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import TIMEZONE
    dt = _parse_dt(update.message.text, TIMEZONE)
    if not dt:
        await update.message.reply_text("❌ Формат неверен. ДД.ММ.ГГГГ ЧЧ:ММ:")
        return States.ADMIN_EVENT_START
    context.user_data['admin_event']['start'] = dt
    await update.message.reply_text("🕐 Введите дату и время окончания (ДД.ММ.ГГГГ ЧЧ:ММ):")
    return States.ADMIN_EVENT_END

async def admin_event_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import TIMEZONE
    dt = _parse_dt(update.message.text, TIMEZONE)
    if not dt:
        await update.message.reply_text("❌ Формат неверен. ДД.ММ.ГГГГ ЧЧ:ММ:")
        return States.ADMIN_EVENT_END
    context.user_data['admin_event']['end'] = dt
    await update.message.reply_text("📝 Введите описание (или 'пропустить'):")
    return States.ADMIN_EVENT_DESC

async def admin_event_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    if desc.lower() in ('пропустить', 'skip', 'нет'):
        desc = None
    data = context.user_data['admin_event']
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events (name, start_time, end_time, description, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (data['name'], data['start'], data['end'], desc, update.effective_user.id))
        event_id = cursor.fetchone()['id']
        conn.commit()
    # Планируем уведомление всем пользователям через 5 минут
    try:
        if context.job_queue:
            context.job_queue.run_once(announce_event_job, when=300, data={'event_id': event_id})
    except Exception:
        pass
    await update.message.reply_text(
        f"✅ Мероприятие создано (ID: {event_id})\n"
        f"📅 {data['name']} | {data['start'].strftime('%d.%m %H:%M')} — {data['end'].strftime('%d.%m %H:%M')}",
        reply_markup=get_main_keyboard(is_admin=True)
    )
    context.user_data.pop('admin_event', None)
    return ConversationHandler.END


# ===============================
# Админ-флоу: Управление постами
# ===============================
async def admin_posts_manage_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await _render_posts_list(query, context)

async def _render_posts_list(query, context):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, text, scheduled_time, status
            FROM posts
            ORDER BY scheduled_time DESC
            LIMIT 20
        ''')
        posts = cursor.fetchall()
    if not posts:
        await query.edit_message_text(
            "🗂 Постов пока нет.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]])
        )
        return States.ADMIN_POST_MANAGE
    text = "🗂 Управление постами (последние 20):\n\n"
    keyboard = []
    from config import TIMEZONE
    from datetime import timezone as dt_tz
    for p in posts:
        dt = p['scheduled_time']
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_tz.utc)
        when = dt.astimezone(TIMEZONE).strftime('%d.%m %H:%M') if dt else '-'
        status = p['status']
        text_part = (p['text'] or '')[:40].replace('\n', ' ')
        keyboard.append([
            InlineKeyboardButton(f"#{p['id']} • {when} • {status}", callback_data='noop')
        ])
        keyboard.append([
            InlineKeyboardButton("✏️ Текст", callback_data=f"post_edit_text_{p['id']}"),
            InlineKeyboardButton("🕐 Время", callback_data=f"post_edit_time_{p['id']}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"post_delete_{p['id']}")
        ])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return States.ADMIN_POST_MANAGE

async def admin_posts_manage_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('post_delete_'):
        post_id = int(data.replace('post_delete_', ''))
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM posts WHERE id = %s', (post_id,))
            conn.commit()
        await query.answer("Удалено", show_alert=False)
        return await _render_posts_list(query, context)
    elif data.startswith('post_edit_text_'):
        post_id = int(data.replace('post_edit_text_', ''))
        context.user_data['edit_post_id'] = post_id
        await query.message.reply_text("Введите новый текст поста (или 'Отмена'):")
        return States.ADMIN_POST_EDIT_TEXT
    elif data.startswith('post_edit_time_'):
        post_id = int(data.replace('post_edit_time_', ''))
        context.user_data['edit_post_id'] = post_id
        await query.message.reply_text("Введите новую дату и время (ДД.ММ.ГГГГ ЧЧ:ММ):")
        return States.ADMIN_POST_EDIT_TIME
    elif data == 'admin_panel':
        # Вернуть в админ-панель через глобальный хендлер
        await query.edit_message_text("Возврат в админ-панель...", reply_markup=get_admin_keyboard())
        return ConversationHandler.END

async def admin_post_edit_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post_id = context.user_data.get('edit_post_id')
    if not post_id:
        await update.message.reply_text("❌ Не найден пост для редактирования.")
        return ConversationHandler.END
    new_text = update.message.text.strip()
    if len(new_text) < 1:
        await update.message.reply_text("❌ Текст пуст. Введите заново:")
        return States.ADMIN_POST_EDIT_TEXT
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE posts SET text = %s WHERE id = %s', (new_text, post_id))
        conn.commit()
    await update.message.reply_text("✅ Текст поста обновлён.")
    # Обновим список
    context.user_data.pop('edit_post_id', None)
    # Отрисуем заново список через сообщ. с кнопками (нужно найти последнее сообщение ботa)
    # Проще — попросим нажать кнопку снова
    await update.message.reply_text("Откройте снова: 🔧 Админ-панель → 🗂 Управление постами")
    return ConversationHandler.END

async def admin_post_edit_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post_id = context.user_data.get('edit_post_id')
    if not post_id:
        await update.message.reply_text("❌ Не найден пост для редактирования.")
        return ConversationHandler.END
    dt = _parse_dt(update.message.text, TIMEZONE)
    if not dt:
        await update.message.reply_text("❌ Неверный формат. ДД.ММ.ГГГГ ЧЧ:ММ:")
        return States.ADMIN_POST_EDIT_TIME
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE posts SET scheduled_time = %s, status = CASE WHEN status = \'sent\' THEN status ELSE \'pending\' END WHERE id = %s', (dt, post_id))
        conn.commit()
    await update.message.reply_text("✅ Время публикации обновлено.")
    context.user_data.pop('edit_post_id', None)
    await update.message.reply_text("Откройте снова: 🔧 Админ-панель → 🗂 Управление постами")
    return ConversationHandler.END

# ===============================
# Админ-флоу: Загрузка в Базу знаний
# ===============================
async def admin_kb_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📚 Загрузка в Базу знаний\n\nВведите заголовок материала:")
    return States.ADMIN_KB_TITLE

async def admin_kb_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    if len(title) < 3:
        await update.message.reply_text("❌ Слишком коротко. Введите заголовок:")
        return States.ADMIN_KB_TITLE
    context.user_data['kb_title'] = title
    await update.message.reply_text("📎 Отправьте файл (документ или фото):")
    return States.ADMIN_KB_FILE

async def admin_kb_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = None
    file_type = None
    if update.message.document:
        file_id = update.message.document.file_id
        file_type = 'document'
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = 'photo'
    else:
        await update.message.reply_text("❌ Отправьте документ или фото:")
        return States.ADMIN_KB_FILE
    kb_id = await upload_to_kb(
        user_id=update.effective_user.id,
        title=context.user_data.get('kb_title', 'Без названия'),
        file_id=file_id,
        file_type=file_type
    )
    await update.message.reply_text(
        f"✅ Материал добавлен в Базу знаний (ID: {kb_id})",
        reply_markup=get_main_keyboard(is_admin=True)
    )
    context.user_data.pop('kb_title', None)
    return ConversationHandler.END

# ===============================
# Админ-флоу: Управление мероприятиями
# ===============================
async def admin_events_manage_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await _render_events_list(query, context)

async def _render_events_list(query, context):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, start_time, end_time
            FROM events
            WHERE end_time >= CURRENT_TIMESTAMP
            ORDER BY start_time
            LIMIT 20
        ''')
        events = cursor.fetchall()
    if not events:
        await query.edit_message_text(
            "🗓 Нет предстоящих мероприятий.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]])
        )
        return States.ADMIN_EVENT_MANAGE
    text = "🗓 Управление мероприятиями (ближайшие 20):\n\n"
    keyboard = []
    from config import TIMEZONE
    from datetime import timezone as dt_tz
    for e in events:
        s = e['start_time']
        if s and s.tzinfo is None:
            s = s.replace(tzinfo=dt_tz.utc)
        when = s.astimezone(TIMEZONE).strftime('%d.%m %H:%M') if s else '-'
        keyboard.append([
            InlineKeyboardButton(f"#{e['id']} • {when} • {e['name'][:20]}", callback_data='noop')
        ])
        keyboard.append([
            InlineKeyboardButton("✏️ Название", callback_data=f"event_edit_name_{e['id']}"),
            InlineKeyboardButton("📝 Описание", callback_data=f"event_edit_desc_{e['id']}"),
            InlineKeyboardButton("🕐 Старт", callback_data=f"event_edit_start_{e['id']}"),
            InlineKeyboardButton("⏱ Конец", callback_data=f"event_edit_end_{e['id']}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"event_delete_{e['id']}")
        ])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return States.ADMIN_EVENT_MANAGE

async def admin_events_manage_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('event_delete_'):
        event_id = int(data.replace('event_delete_', ''))
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM events WHERE id = %s', (event_id,))
            conn.commit()
        await query.answer("Удалено", show_alert=False)
        return await _render_events_list(query, context)
    elif data.startswith('event_edit_name_'):
        event_id = int(data.replace('event_edit_name_', ''))
        context.user_data['edit_event_id'] = event_id
        await query.message.reply_text("Введите новое название:")
        return States.ADMIN_EVENT_EDIT_NAME
    elif data.startswith('event_edit_desc_'):
        event_id = int(data.replace('event_edit_desc_', ''))
        context.user_data['edit_event_id'] = event_id
        await query.message.reply_text("Введите новое описание (или 'пропустить' чтобы очистить):")
        return States.ADMIN_EVENT_EDIT_DESC
    elif data.startswith('event_edit_start_'):
        event_id = int(data.replace('event_edit_start_', ''))
        context.user_data['edit_event_id'] = event_id
        await query.message.reply_text("Введите новую дату и время начала (ДД.ММ.ГГГГ ЧЧ:ММ):")
        return States.ADMIN_EVENT_EDIT_START
    elif data.startswith('event_edit_end_'):
        event_id = int(data.replace('event_edit_end_', ''))
        context.user_data['edit_event_id'] = event_id
        await query.message.reply_text("Введите новую дату и время окончания (ДД.ММ.ГГГГ ЧЧ:ММ):")
        return States.ADMIN_EVENT_EDIT_END
    elif data == 'admin_panel':
        await query.edit_message_text("Возврат в админ-панель...", reply_markup=get_admin_keyboard())
        return ConversationHandler.END

async def admin_event_edit_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_id = context.user_data.get('edit_event_id')
    if not event_id:
        return ConversationHandler.END
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("❌ Слишком коротко. Введите снова:")
        return States.ADMIN_EVENT_EDIT_NAME
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE events SET name = %s WHERE id = %s', (name, event_id))
        conn.commit()
    await update.message.reply_text("✅ Название обновлено.")
    context.user_data.pop('edit_event_id', None)
    await update.message.reply_text("Откройте снова: 🔧 Админ-панель → 🗓 Управление мероприятиями")
    return ConversationHandler.END

async def admin_event_edit_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_id = context.user_data.get('edit_event_id')
    if not event_id:
        return ConversationHandler.END
    desc = update.message.text.strip()
    if desc.lower() in ('пропустить', 'skip'):
        desc = None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE events SET description = %s WHERE id = %s', (desc, event_id))
        conn.commit()
    await update.message.reply_text("✅ Описание обновлено.")
    context.user_data.pop('edit_event_id', None)
    await update.message.reply_text("Откройте снова: 🔧 Админ-панель → 🗓 Управление мероприятиями")
    return ConversationHandler.END

async def admin_event_edit_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_id = context.user_data.get('edit_event_id')
    if not event_id:
        return ConversationHandler.END
    dt = _parse_dt(update.message.text, TIMEZONE)
    if not dt:
        await update.message.reply_text("❌ Неверный формат. ДД.ММ.ГГГГ ЧЧ:ММ:")
        return States.ADMIN_EVENT_EDIT_START
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE events SET start_time = %s WHERE id = %s', (dt, event_id))
        conn.commit()
    await update.message.reply_text("✅ Время начала обновлено.")
    context.user_data.pop('edit_event_id', None)
    await update.message.reply_text("Откройте снова: 🔧 Админ-панель → 🗓 Управление мероприятиями")
    return ConversationHandler.END

async def admin_event_edit_end_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_id = context.user_data.get('edit_event_id')
    if not event_id:
        return ConversationHandler.END
    dt = _parse_dt(update.message.text, TIMEZONE)
    if not dt:
        await update.message.reply_text("❌ Неверный формат. ДД.ММ.ГГГГ ЧЧ:ММ:")
        return States.ADMIN_EVENT_EDIT_END
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE events SET end_time = %s WHERE id = %s', (dt, event_id))
        conn.commit()
    await update.message.reply_text("✅ Время окончания обновлено.")
    context.user_data.pop('edit_event_id', None)
    await update.message.reply_text("Откройте снова: 🔧 Админ-панель → 🗓 Управление мероприятиями")
    return ConversationHandler.END

# ===============================
# Админ-флоу: Управление Базой знаний
# ===============================
async def admin_kb_manage_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await _render_kb_list(query, context)

async def _render_kb_list(query, context):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, title, file_type
            FROM knowledge_base
            ORDER BY upload_time DESC
            LIMIT 20
        ''')
        files = cursor.fetchall()
    if not files:
        await query.edit_message_text(
            "📚 База знаний пуста.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]])
        )
        return States.ADMIN_KB_MANAGE
    text = "🗃 Управление Базой знаний (последние 20):\n\n"
    keyboard = []
    for f in files:
        keyboard.append([InlineKeyboardButton(f"#{f['id']} • {f['title'][:25]}", callback_data='noop')])
        keyboard.append([
            InlineKeyboardButton("✏️ Переименовать", callback_data=f"kb_rename_{f['id']}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"kb_delete_{f['id']}")
        ])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return States.ADMIN_KB_MANAGE

async def admin_kb_manage_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('kb_delete_'):
        kb_id = int(data.replace('kb_delete_', ''))
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM knowledge_base WHERE id = %s', (kb_id,))
            conn.commit()
        await query.answer("Удалено", show_alert=False)
        return await _render_kb_list(query, context)
    elif data.startswith('kb_rename_'):
        kb_id = int(data.replace('kb_rename_', ''))
        context.user_data['rename_kb_id'] = kb_id
        await query.message.reply_text("Введите новое имя файла:")
        return States.ADMIN_KB_RENAME
    elif data == 'admin_panel':
        await query.edit_message_text("Возврат в админ-панель...", reply_markup=get_admin_keyboard())
        return ConversationHandler.END

async def admin_kb_rename_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb_id = context.user_data.get('rename_kb_id')
    if not kb_id:
        return ConversationHandler.END
    title = update.message.text.strip()
    if len(title) < 1:
        await update.message.reply_text("❌ Пустое имя. Введите снова:")
        return States.ADMIN_KB_RENAME
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE knowledge_base SET title = %s WHERE id = %s', (title, kb_id))
        conn.commit()
    await update.message.reply_text("✅ Имя обновлено.")
    context.user_data.pop('rename_kb_id', None)
    await update.message.reply_text("Откройте снова: 🔧 Админ-панель → 🗃 Управление Базой знаний")
    return ConversationHandler.END


async def admin_cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена любого админ-диалога."""
    try:
        if getattr(update, 'callback_query', None):
            await update.callback_query.answer("Действие отменено")
            await update.callback_query.message.reply_text(
                "❌ Действие отменено.", reply_markup=get_main_keyboard(is_admin=True)
            )
        elif getattr(update, 'message', None):
            await update.message.reply_text(
                "❌ Действие отменено.", reply_markup=get_main_keyboard(is_admin=True)
            )
    except Exception:
        pass
    for key in ('admin_post', 'admin_event', 'kb_title'):
        context.user_data.pop(key, None)
    return ConversationHandler.END


def get_admin_handler():
    """ConversationHandler для админ-флоу (создание/управление постами, мероприятиями, БЗ и конкурсом)."""
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    from handlers.contests import (
        admin_contest_start_begin,
        admin_contest_edit_time_begin,
        admin_contest_set_endtime_input,
    )
    return ConversationHandler(
        entry_points=[
            # Создание
            CallbackQueryHandler(admin_post_start, pattern='^admin_create_post$'),
            CallbackQueryHandler(admin_event_start, pattern='^admin_create_event$'),
            CallbackQueryHandler(admin_kb_start, pattern='^admin_upload_kb$'),
            CallbackQueryHandler(admin_contest_start_begin, pattern='^admin_contest_start$'),
            CallbackQueryHandler(admin_contest_edit_time_begin, pattern='^admin_contest_edit_time$'),
            # Управление
            CallbackQueryHandler(admin_posts_manage_start, pattern='^admin_manage_posts$'),
            CallbackQueryHandler(admin_events_manage_start, pattern='^admin_manage_events$'),
            CallbackQueryHandler(admin_kb_manage_start, pattern='^admin_manage_kb$'),
        ],
        states={
            # Посты: создание
            States.ADMIN_POST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_text)],
            States.ADMIN_POST_MEDIA: [
                MessageHandler(filters.PHOTO, admin_post_media),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_media)
            ],
            States.ADMIN_POST_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_datetime)],
            # Посты: управление
            States.ADMIN_POST_MANAGE: [
                CallbackQueryHandler(admin_posts_manage_cb, pattern='^(post_edit_text_|post_edit_time_|post_delete_|admin_panel)$')
            ],
            States.ADMIN_POST_EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_edit_text_input)],
            States.ADMIN_POST_EDIT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_edit_time_input)],

            # События: создание
            States.ADMIN_EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_name)],
            States.ADMIN_EVENT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_start_time)],
            States.ADMIN_EVENT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_end_time)],
            States.ADMIN_EVENT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_desc)],
            # События: управление
            States.ADMIN_EVENT_MANAGE: [
                CallbackQueryHandler(admin_events_manage_cb, pattern='^(event_edit_name_|event_edit_desc_|event_edit_start_|event_edit_end_|event_delete_|admin_panel)$')
            ],
            States.ADMIN_EVENT_EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_edit_name_input)],
            States.ADMIN_EVENT_EDIT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_edit_desc_input)],
            States.ADMIN_EVENT_EDIT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_edit_start_input)],
            States.ADMIN_EVENT_EDIT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_edit_end_input)],

            # База знаний: загрузка
            States.ADMIN_KB_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_kb_title)],
            States.ADMIN_KB_FILE: [
                MessageHandler(filters.Document.ALL, admin_kb_file),
                MessageHandler(filters.PHOTO, admin_kb_file)
            ],
            # База знаний: управление
            States.ADMIN_KB_MANAGE: [
                CallbackQueryHandler(admin_kb_manage_cb, pattern='^(kb_rename_|kb_delete_|admin_panel)$')
            ],
            States.ADMIN_KB_RENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_kb_rename_input)],
            # Конкурс фото: ввод времени окончания
            States.ADMIN_CONTEST_ENDTIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_contest_set_endtime_input)],
        },
        fallbacks=[
            CallbackQueryHandler(admin_cancel_conv, pattern='^admin_cancel$'),
            MessageHandler(filters.Regex('^(Отмена|отмена|Cancel|cancel)$'), admin_cancel_conv),
        ],
        name="admin_flows",
        persistent=False
    )

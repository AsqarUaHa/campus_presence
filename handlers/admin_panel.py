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
    
    elif data == 'admin_events_archive':
        await show_events_archive(query, context)
    
    elif data == 'admin_export_data':
        await show_export_menu(query, context)

    elif data == 'admin_photo_contest':
        await show_photo_contest_menu(query)
    elif data == 'admin_contest_start':
        await start_photo_contest(update, context)
    elif data == 'admin_contest_view':
        await view_contest_photos(update, context)
    elif data == 'admin_contest_end'
        # end_photo_contest ожидает context, оборачиваем вызов
        await end_photo_contest(context)
    
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
    keyboard = [
        [InlineKeyboardButton("🚀 Запустить конкурс", callback_data='admin_contest_start')],
        [InlineKeyboardButton("🖼 Посмотреть фото", callback_data='admin_contest_view')],
        [InlineKeyboardButton("🏁 Завершить конкурс", callback_data='admin_contest_end')],
        [InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')],
    ]
    await query.edit_message_text(
        "📸 Конкурс фото — выберите действие:",
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
    await update.message.reply_text(
        f"✅ Мероприятие создано (ID: {event_id})\n"
        f"📅 {data['name']} | {data['start'].strftime('%d.%m %H:%M')} — {data['end'].strftime('%d.%m %H:%M')}",
        reply_markup=get_main_keyboard(is_admin=True)
    )
    context.user_data.pop('admin_event', None)
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


def get_admin_handler():
    """ConversationHandler для админ-флоу (посты/мероприятия/БЗ)."""
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_post_start, pattern='^admin_create_post$'),
            CallbackQueryHandler(admin_event_start, pattern='^admin_create_event$'),
            CallbackQueryHandler(admin_kb_start, pattern='^admin_upload_kb$'),
        ],
        states={
            States.ADMIN_POST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_text)],
            States.ADMIN_POST_MEDIA: [
                MessageHandler(filters.PHOTO, admin_post_media),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_media)
            ],
            States.ADMIN_POST_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_datetime)],

            States.ADMIN_EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_name)],
            States.ADMIN_EVENT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_start_time)],
            States.ADMIN_EVENT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_end_time)],
            States.ADMIN_EVENT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_desc)],

            States.ADMIN_KB_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_kb_title)],
            States.ADMIN_KB_FILE: [
                MessageHandler(filters.Document.ALL, admin_kb_file),
                MessageHandler(filters.PHOTO, admin_kb_file)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(admin_cancel_conv, pattern='^admin_cancel$'),
            MessageHandler(filters.Regex('^(Отмена|отмена|Cancel|cancel)$'), admin_cancel_conv),
        ],
        name="admin_flows",
        persistent=False
    )

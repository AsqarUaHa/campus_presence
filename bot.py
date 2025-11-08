# ============================================
# bot.py - Campus Check-in Bot v2
# Полнофункциональная версия
# ============================================

import os
import logging
from threading import Thread
from datetime import time
from flask import Flask

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)

# Конфигурация
from config import BOT_TOKEN, TIMEZONE_OFFSET, ADMIN_IDS, States

# Database
from database.models import (
    init_database,
    is_user_registered,
    create_user,
    is_user_admin
)

# Handlers
from handlers.registration import (
    start_registration,
    registration_first_name,
    registration_last_name,
    registration_birth_date,
    registration_team_role,
    registration_phone,
    cancel_registration
)
from handlers.checkin import (
    request_checkin_location,
    checkout,
    handle_checkin_location,
    handle_location_update
)
from handlers.user_menu import (
    show_my_status,
    show_who_inside,
    show_all_participants,
    show_settings,
    show_knowledge_base,
    handle_settings_callback,
    handle_knowledge_base_callback
)
from handlers.admin_panel import (
    show_admin_panel,
    handle_admin_callback,
    handle_profile_view,
    handle_event_details
)

# Features
from features.export_data import export_presence_data
from features.posts_scheduler import check_scheduled_posts, create_post
from features.knowledge_base import upload_to_kb, handle_kb_file
from handlers.contests import (
    start_photo_contest,
    upload_contest_photo,
    view_contest_photos,
    end_photo_contest,
    vote_for_photo
)

# Utils
from utils.keyboards import get_main_keyboard
from utils.decorators import registered_only, admin_only

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "🎓 Campus Check-in Bot v2 is running! ✅"

@app.route('/health')
def health():
    return {
        "status": "ok",
        "version": "2.0",
        "features": [
            "registration",
            "checkin",
            "ranks",
            "admin_panel",
            "export",
            "posts",
            "contests",
            "knowledge_base"
        ]
    }

def run_flask():
    """Запуск Flask в отдельном потоке"""
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)


# ============================================
# Основные команды
# ============================================

async def start(update: Update, context):
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    # Создаём пользователя если новый
    create_user(user_id, user.username or "Без username", user.full_name)
    
    # Проверяем регистрацию
    if not is_user_registered(user_id):
        # Запускаем регистрацию
        return await start_registration(update, context)
    
    # Пользователь зарегистрирован
    is_admin = is_user_admin(user_id)
    
    welcome_text = f"""
👋 Добро пожаловать, {user.first_name}!

🎓 Campus Check-in Bot v2

Используйте меню для работы с ботом.
    """
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(is_admin)
    )


async def help_command(update: Update, context):
    """Справка по командам"""
    help_text = """
❓ **Справка по использованию бота**

**Основные функции:**
📍 Я в кампусе - Отметиться с геолокацией
🚪 Я ухожу - Отметить уход
👥 Кто в кампусе - Список присутствующих
👤 Все участники - Все с индикаторами статуса
📊 Мой статус - Ваша информация и статистика
📚 База знаний - Материалы и документы
⚙️ Настройки - Управление профилем

**Система рангов:**
🌱 Новичок (0+ отметок)
💡 Идеолог (5+ отметок)
🔥 Реформатор (15+ отметок)
🧠 Философ (30+ отметок)

**Индикаторы статуса:**
🟢 В кампусе (активный check-in)
🟡 Рядом (< 1000м, < 30 мин)
🔴 Вне кампуса

**Важно:**
⚠️ Для check-in необходимо находиться в пределах 300м от кампуса!
📱 Геолокацию можно отправить только с мобильного приложения или web.telegram.org

**Команды:**
/start - Начать работу
/help - Эта справка
/cancel - Отменить текущее действие
    """
    
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())


# ============================================
# Обработка текстовых команд из меню
# ============================================

@registered_only
async def handle_text_commands(update: Update, context):
    """Обработка текстовых команд из меню"""
    text = update.message.text
    user_id = update.effective_user.id
    is_admin = is_user_admin(user_id)
    
    if text == "📍 Я в кампусе":
        await request_checkin_location(update, context)
    
    elif text == "🚪 Я ухожу":
        await checkout(update, context)
    
    elif text == "📊 Мой статус":
        await show_my_status(update, context)
    
    elif text == "👥 Кто в кампусе":
        await show_who_inside(update, context)
    
    elif text == "👤 Все участники":
        await show_all_participants(update, context)
    
    elif text == "📚 База знаний":
        await show_knowledge_base(update, context)
    
    elif text == "⚙️ Настройки":
        await show_settings(update, context)
    
    elif text == "🔧 Админ-панель" and is_admin:
        await show_admin_panel(update, context)
    
    elif text == "📸 Загрузить фото":
        await upload_contest_photo(update, context)
    
    elif text == "❓ Помощь":
        await help_command(update, context)
    
    elif text == "❌ Отмена":
        await update.message.reply_text(
            "Действие отменено.",
            reply_markup=get_main_keyboard(is_admin)
        )


# ============================================
# Обработка callback-запросов
# ============================================

async def handle_callbacks(update: Update, context):
    """Центральный обработчик всех callback"""
    query = update.callback_query
    data = query.data
    
    # Настройки
    if data in ['toggle_geo', 'edit_profile', 'my_stats', 'settings_close']:
        await handle_settings_callback(update, context)
    
    # База знаний
    elif data.startswith('kb_'):
        await handle_knowledge_base_callback(update, context)
    
    # Админ-панель
    elif data.startswith('admin_'):
        if data.startswith('admin_profile_'):
            await handle_profile_view(update, context)
        elif data.startswith('admin_event_'):
            await handle_event_details(update, context)
        else:
            await handle_admin_callback(update, context)
    
    # Экспорт данных
    elif data.startswith('export_'):
        if data == 'export_today':
            await export_presence_data(update, context, 'today')
        elif data == 'export_week':
            await export_presence_data(update, context, 'week')
        elif data == 'export_month':
            await export_presence_data(update, context, 'month')
        elif data.startswith('export_event_'):
            event_id = int(data.replace('export_event_', ''))
            await export_presence_data(update, context, 'event', event_id)
    
    # Конкурс фото
    elif data == 'contest_start':
        await start_photo_contest(update, context)
    elif data == 'contest_view':
        await view_contest_photos(update, context)
    elif data.startswith('vote_'):
        await vote_for_photo(update, context)
    
    else:
        await query.answer()


# ============================================
# ConversationHandler для создания постов
# ============================================

async def admin_post_text(update: Update, context):
    """Получение текста поста"""
    text = update.message.text
    context.user_data['post_text'] = text
    
    await update.message.reply_text(
        f"✅ Текст поста сохранён.\n\n"
        f"Хотите добавить медиа (фото)?\n"
        f"Отправьте фото или нажмите /skip для пропуска."
    )
    return States.ADMIN_POST_MEDIA


async def admin_post_media(update: Update, context):
    """Получение медиа для поста"""
    if update.message.photo:
        photo = update.message.photo[-1]
        context.user_data['post_media'] = photo.file_id
        await update.message.reply_text("✅ Фото добавлено.")
    
    await update.message.reply_text(
        "📅 Введите дату и время публикации в формате:\n"
        "ДД.ММ.ГГГГ ЧЧ:ММ\n\n"
        "Например: 15.11.2024 18:00"
    )
    return States.ADMIN_POST_DATETIME


async def admin_post_skip_media(update: Update, context):
    """Пропуск медиа"""
    await update.message.reply_text(
        "📅 Введите дату и время публикации в формате:\n"
        "ДД.ММ.ГГГГ ЧЧ:ММ\n\n"
        "Например: 15.11.2024 18:00"
    )
    return States.ADMIN_POST_DATETIME


async def admin_post_datetime(update: Update, context):
    """Получение времени публикации"""
    from datetime import datetime
    from config import TIMEZONE
    
    try:
        dt_str = update.message.text.strip()
        scheduled_time = datetime.strptime(dt_str, '%d.%m.%Y %H:%M')
        scheduled_time = scheduled_time.replace(tzinfo=TIMEZONE)
        
        # Создаём пост
        user_id = update.effective_user.id
        text = context.user_data['post_text']
        media = context.user_data.get('post_media')
        
        post_id = await create_post(user_id, text, media, scheduled_time)
        
        await update.message.reply_text(
            f"✅ Пост создан!\n\n"
            f"ID: {post_id}\n"
            f"📅 Публикация: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Пост будет автоматически разослан в указанное время.",
            reply_markup=get_main_keyboard(is_admin=True)
        )
        
        context.user_data.clear()
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты!\n"
            "Используйте: ДД.ММ.ГГГГ ЧЧ:ММ"
        )
        return States.ADMIN_POST_DATETIME


# ============================================
# ConversationHandler для создания мероприятия
# ============================================

async def admin_event_name(update: Update, context):
    """Получение названия мероприятия"""
    name = update.message.text
    context.user_data['event_name'] = name
    
    await update.message.reply_text(
        f"✅ Название: {name}\n\n"
        f"Введите дату и время начала в формате:\n"
        f"ДД.ММ.ГГГГ ЧЧ:ММ"
    )
    return States.ADMIN_EVENT_START


async def admin_event_start(update: Update, context):
    """Получение времени начала"""
    from datetime import datetime
    from config import TIMEZONE
    
    try:
        dt_str = update.message.text.strip()
        start_time = datetime.strptime(dt_str, '%d.%m.%Y %H:%M')
        start_time = start_time.replace(tzinfo=TIMEZONE)
        context.user_data['event_start'] = start_time
        
        await update.message.reply_text(
            f"✅ Начало: {start_time.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Введите дату и время окончания:"
        )
        return States.ADMIN_EVENT_END
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат! Попробуйте снова:")
        return States.ADMIN_EVENT_START


async def admin_event_end(update: Update, context):
    """Получение времени окончания"""
    from datetime import datetime
    from config import TIMEZONE
    
    try:
        dt_str = update.message.text.strip()
        end_time = datetime.strptime(dt_str, '%d.%m.%Y %H:%M')
        end_time = end_time.replace(tzinfo=TIMEZONE)
        context.user_data['event_end'] = end_time
        
        await update.message.reply_text(
            f"✅ Окончание: {end_time.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Введите описание мероприятия (или /skip):"
        )
        return States.ADMIN_EVENT_DESC
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат! Попробуйте снова:")
        return States.ADMIN_EVENT_END


async def admin_event_desc(update: Update, context):
    """Получение описания мероприятия"""
    from database.db_manager import get_db
    
    description = update.message.text
    user_id = update.effective_user.id
    
    name = context.user_data['event_name']
    start = context.user_data['event_start']
    end = context.user_data['event_end']
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events (name, start_time, end_time, description, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, start, end, description, user_id))
        event_id = cursor.fetchone()['id']
        conn.commit()
    
    await update.message.reply_text(
        f"✅ Мероприятие создано!\n\n"
        f"ID: {event_id}\n"
        f"Название: {name}\n"
        f"📅 {start.strftime('%d.%m.%Y %H:%M')} - {end.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=get_main_keyboard(is_admin=True)
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def admin_event_skip_desc(update: Update, context):
    """Пропуск описания"""
    return await admin_event_desc(update, context)


# ============================================
# ConversationHandler для базы знаний
# ============================================

async def admin_kb_title(update: Update, context):
    """Получение названия материала"""
    title = update.message.text
    context.user_data['kb_title'] = title
    
    await update.message.reply_text(
        f"✅ Название: {title}\n\n"
        f"Отправьте файл (документ):"
    )
    return States.ADMIN_KB_FILE


async def admin_kb_file(update: Update, context):
    """Получение файла"""
    from database.db_manager import get_db
    
    if not update.message.document:
        await update.message.reply_text("❌ Пожалуйста, отправьте документ!")
        return States.ADMIN_KB_FILE
    
    document = update.message.document
    user_id = update.effective_user.id
    title = context.user_data['kb_title']
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO knowledge_base (title, file_id, file_type, uploaded_by)
            VALUES (%s, %s, 'document', %s)
            RETURNING id
        ''', (title, document.file_id, user_id))
        kb_id = cursor.fetchone()['id']
        conn.commit()
    
    await update.message.reply_text(
        f"✅ Материал добавлен в Базу Знаний!\n\n"
        f"ID: {kb_id}\n"
        f"Название: {title}\n"
        f"Файл: {document.file_name}",
        reply_markup=get_main_keyboard(is_admin=True)
    )
    
    context.user_data.clear()
    return ConversationHandler.END


# ============================================
# Главная функция
# ============================================

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        return
    
    # Инициализация БД
    try:
        init_database()
        logger.info("✅ База данных инициализирована")
        
        # Добавляем админов из переменной окружения
        if ADMIN_IDS:
            from database.db_manager import get_db
            with get_db() as conn:
                cursor = conn.cursor()
                for admin_id in ADMIN_IDS:
                    cursor.execute(
                        'UPDATE users SET is_admin = TRUE WHERE user_id = %s',
                        (admin_id,)
                    )
                conn.commit()
            logger.info(f"✅ Добавлено {len(ADMIN_IDS)} администраторов")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")
        return
    
    # Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask запущен для Render")
    
    # Telegram Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Job queue для автопостов и конкурсов
    job_queue = application.job_queue
    
    # Проверка постов каждую минуту
    job_queue.run_repeating(check_scheduled_posts, interval=60, first=10)
    
    # Завершение конкурса в 02:00
    job_queue.run_daily(end_photo_contest, time=time(hour=2, minute=0, tzinfo=TIMEZONE))
    
    logger.info("✅ Планировщик задач запущен")
    
    # ConversationHandler для регистрации
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            States.REGISTRATION_FIRST_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration_first_name)
            ],
            States.REGISTRATION_LAST_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration_last_name)
            ],
            States.REGISTRATION_BIRTH_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration_birth_date)
            ],
            States.REGISTRATION_TEAM_ROLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration_team_role)
            ],
            States.REGISTRATION_PHONE: [
                MessageHandler(
                    (filters.TEXT | filters.CONTACT) & ~filters.COMMAND,
                    registration_phone
                )
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_registration)],
    )
    
    # ConversationHandler для создания постов
    create_post_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: States.ADMIN_POST_TEXT, pattern='^admin_create_post$')],
        states={
            States.ADMIN_POST_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_text)
            ],
            States.ADMIN_POST_MEDIA: [
                MessageHandler(filters.PHOTO, admin_post_media),
                CommandHandler('skip', admin_post_skip_media)
            ],
            States.ADMIN_POST_DATETIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_post_datetime)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_registration)],
    )
    
    # ConversationHandler для создания мероприятий
    create_event_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: States.ADMIN_EVENT_NAME, pattern='^admin_create_event$')],
        states={
            States.ADMIN_EVENT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_name)
            ],
            States.ADMIN_EVENT_START: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_start)
            ],
            States.ADMIN_EVENT_END: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_end)
            ],
            States.ADMIN_EVENT_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_event_desc),
                CommandHandler('skip', admin_event_skip_desc)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_registration)],
    )
    
    # ConversationHandler для базы знаний
    kb_upload_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u, c: States.ADMIN_KB_TITLE, pattern='^admin_upload_kb$')],
        states={
            States.ADMIN_KB_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_kb_title)
            ],
            States.ADMIN_KB_FILE: [
                MessageHandler(filters.Document.ALL, admin_kb_file)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel_registration)],
    )
    
    # Регистрируем handlers
    application.add_handler(registration_handler)
    application.add_handler(create_post_handler)
    application.add_handler(create_event_handler)
    application.add_handler(kb_upload_handler)
    
    # Команды
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработка геолокации
    application.add_handler(MessageHandler(
        filters.LOCATION,
        lambda u, c: handle_checkin_location(u, c) if c.user_data.get('awaiting_checkin_location') 
        else handle_location_update(u, c)
    ))
    
    # Обработка фото для конкурса
    application.add_handler(MessageHandler(filters.PHOTO, upload_contest_photo))
    
    # Текстовые команды из меню
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_commands
    ))
    
    # Callback для inline-кнопок
    application.add_handler(CallbackQueryHandler(handle_callbacks))
    
    logger.info("=" * 50)
    logger.info("🎓 Campus Check-in Bot v2 запущен!")
    logger.info("=" * 50)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

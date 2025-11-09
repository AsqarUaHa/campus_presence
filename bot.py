# ============================================
# bot.py - Campus Check-in Bot v2 (ФИНАЛЬНАЯ ВЕРСИЯ)
# Полнофункциональная версия со всеми модулями
# ============================================

import os
import logging
from threading import Thread
from datetime import time as dt_time
from flask import Flask

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# Конфигурация
from config import BOT_TOKEN, TIMEZONE_OFFSET, ADMIN_IDS, TIMEZONE

# Database
from database.db_manager import (
    init_connection_pool,
    test_connection,
    get_table_stats,
    close_connection_pool
)
from database.models import (
    init_database,
    is_user_registered,
    create_user,
    is_user_admin,
    get_user_profile,
    get_all_users_status
)

# Handlers
from handlers.registration import (
    start_registration,
    get_registration_handler
)
from handlers.admin_panel import get_admin_handler
from handlers.contests import upload_contest_photo, end_photo_contest
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
from features.ranks import (
    get_leaderboard,
    get_user_rank_info
)
from features.export_data import export_presence_data
from features.posts_scheduler import check_scheduled_posts

# Utils
from utils.keyboards import get_main_keyboard

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
    try:
        stats = get_table_stats()
        return {
            "status": "ok",
            "version": "2.0",
            "database": stats
        }
    except:
        return {"status": "ok", "version": "2.0"}

def run_flask():
    """Запуск Flask в отдельном потоке"""
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)


# ============================================
# ОСНОВНЫЕ КОМАНДЫ
# ============================================

async def start(update: Update, context):
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    create_user(user_id, user.username or "Без username", user.full_name)

    
    # Гарантируем, что админ сразу видит админ‑кнопку, даже если его записи не было при старте бота
    from config import ADMIN_IDS
    if user_id in ADMIN_IDS:
        try:
            from database.db_manager import get_db
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET is_admin = TRUE WHERE user_id = %s', (user_id,))
                conn.commit()
        except Exception:
            pass
            
    if not is_user_registered(user_id):
        return await start_registration(update, context)
    
    is_admin = is_user_admin(user_id)
    
    welcome_text = f"""
👋 Добро пожаловать, {user.first_name}!

🎓 **Campus Check-in Bot v2**

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
📍 Я в кампусе - Отметиться с геолокацией (≤300м)
🚪 Я ухожу - Отметить уход
👥 Кто в кампусе - Список присутствующих
👤 Все участники - Все с индикаторами 🟢🟡🔴
📊 Мой статус - Профиль, ранг, статистика
📚 База знаний - Материалы и документы
⚙️ Настройки - Управление профилем

**Система рангов:**
🌱 Новичок (0+ отметок)
💡 Идеолог (5+ отметок)
🔥 Реформатор (15+ отметок)
🧠 Философ (30+ отметок)

**Команды:**
/start - Начать работу
/status - Мой статус и ранг
/leaderboard - Таблица лидеров
/help - Эта справка

⚠️ Для check-in необходимо находиться в пределах 300м от кампуса!
📱 Геолокацию можно отправить только с мобильного приложения
    """
    
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())


async def status_command(update: Update, context):
    """Команда /status - показать статус"""
    if not is_user_registered(update.effective_user.id):
        await update.message.reply_text("❌ Сначала пройдите регистрацию. Отправьте /start")
        return
    
    await show_my_status(update, context)


async def leaderboard_command(update: Update, context):
    """Команда /leaderboard - таблица лидеров"""
    if not is_user_registered(update.effective_user.id):
        await update.message.reply_text("❌ Сначала пройдите регистрацию. Отправьте /start")
        return
    
    leaders = get_leaderboard(limit=10)
    
    if not leaders:
        await update.message.reply_text(
            "📊 Таблица лидеров пока пуста.",
            reply_markup=get_main_keyboard()
        )
        return
    
    text = "🏆 **Таблица лидеров**\n\n"
    text += "Топ-10 участников по рангам:\n\n"
    
    for i, leader in enumerate(leaders, 1):
        emoji = leader['emoji']
        name = f"{leader['first_name']} {leader['last_name']}"
        checkins = leader['total_checkins']
        rank = leader['current_rank']
        
        text += f"{i}. {emoji} {name}\n"
        text += f"   └ {rank} • {checkins} отметок\n\n"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())


async def rank_info_command(update: Update, context):
    """Команда /rank - информация о ранге"""
    if not is_user_registered(update.effective_user.id):
        await update.message.reply_text("❌ Сначала пройдите регистрацию. Отправьте /start")
        return
    
    user_id = update.effective_user.id
    rank_info = get_user_rank_info(user_id)
    
    if not rank_info:
        await update.message.reply_text("❌ Ошибка получения информации о ранге")
        return
    
    text = f"""
{rank_info['emoji']} **Ваш ранг: {rank_info['current_rank']}**

📈 Всего отметок: {rank_info['total_checkins']}
    """
    
    if rank_info['next_rank']:
        next_rank = rank_info['next_rank']
        text += f"\n🎯 **Следующий ранг: {next_rank['name']} {next_rank['emoji']}**\n"
        text += f"Необходимо: {next_rank['min_checkins']} отметок\n"
        text += f"Осталось: {next_rank['remaining']} отметок"
    else:
        text += "\n\n🏆 **Вы достигли максимального ранга!**"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())


# ============================================
# ОБРАБОТКА ТЕКСТОВЫХ КОМАНД
# ============================================

async def handle_text_commands(update: Update, context):
    """Обработка текстовых команд из меню"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if not is_user_registered(user_id):
        await update.message.reply_text("❌ Сначала пройдите регистрацию. Отправьте /start")
        return
    
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
    
    elif text == "❓ Помощь":
        await help_command(update, context)
    
    elif text == "❌ Отмена":
        await update.message.reply_text(
            "Действие отменено.",
            reply_markup=get_main_keyboard(is_admin)
        )


# ============================================
# ОБРАБОТКА CALLBACK
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

    # Конкурс фото (пользовательские действия)
    elif data.startswith('contest_'):
        from handlers.contests import handle_contest_callback
        await handle_contest_callback(update, context)
    
    else:
        await query.answer()

# ============================================
# ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ ОШИБОК
# ============================================

async def global_error_handler(update: Update, context):
    logger.error("Unhandled error in handler", exc_info=context.error)
    try:
        if update and getattr(update, 'effective_chat', None):
            # Мягкое уведомление админу/пользователю (без падения приложения)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Произошла ошибка. Мы уже разбираемся.")
    except Exception:
        pass

# ============================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================


def main():
    """Запуск бота"""
    logger.info("=" * 60)
    logger.info("🎓 Campus Check-in Bot v2 - Запуск")
    logger.info("=" * 60)
    
    # Проверка токена
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        return
    
    # Инициализация пула соединений
    try:
        init_connection_pool(minconn=2, maxconn=10)
    except Exception as e:
        logger.warning(f"⚠️ Пул соединений не создан: {e}")
    
    # Тестирование подключения к БД
    if not test_connection():
        logger.error("❌ Не удалось подключиться к БД!")
        return
    
    # Инициализация БД
    try:
        init_database()
        logger.info("✅ База данных инициализирована")
        
        # Статистика таблиц
        stats = get_table_stats()
        logger.info("📊 Статистика БД:")
        for table, count in stats.items():
            logger.info(f"   {table}: {count} записей")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        return
    
    # Добавляем админов
    if ADMIN_IDS:
        from database.db_manager import get_db
        try:
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
            logger.warning(f"⚠️ Ошибка добавления админов: {e}")
    
    # Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask запущен для Render")
    
     # Telegram Application (with job queue enabled)
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
    
    # Глобальный обработчик ошибок, чтобы исключения в handlers/jobs не валили приложение
    application.add_error_handler(global_error_handler)
    # Job queue для автопостов
    job_queue = application.job_queue
    
    if job_queue:
        # Проверка постов каждую минуту
        job_queue.run_repeating(check_scheduled_posts, interval=60, first=10)
        logger.info("✅ Планировщик автопостов запущен")
    else:
        logger.warning("⚠️ Job queue недоступен. Установите: pip install 'python-telegram-bot[job-queue]'")
    
        # План: автоматическое завершение фотоконкурса ежедневно в заданное время
        try:
            from config import CONTEST_END_TIME, TIMEZONE
            hh, mm = [int(x) for x in CONTEST_END_TIME.split(':')]
            application.job_queue.run_daily(
                end_photo_contest,
                time=dt_time(hour=hh, minute=mm, tzinfo=TIMEZONE),
                name="end_photo_contest"
            )
            logger.info(f"✅ Планировщик завершения конкурса фото: {hh:02d}:{mm:02d}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось назначить завершение конкурса: {e}")
    # ConversationHandler для регистрации
    registration_handler = get_registration_handler()
    application.add_handler(registration_handler)

    
    # ConversationHandler для админ-фич (создать пост/мероприятие/загрузка в БЗ)
    admin_handler = get_admin_handler()
    application.add_handler(admin_handler)
    # Команды
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("rank", rank_info_command))
    
    # Обработка геолокации
    async def location_handler(update: Update, context):
        if context.user_data.get('awaiting_checkin_location'):
            await handle_checkin_location(update, context)
        else:
            await handle_location_update(update, context)
    
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))

    
    # Загрузка фото на конкурс (глобальный обработчик фото)
    application.add_handler(MessageHandler(filters.PHOTO, upload_contest_photo))
    # Текстовые команды из меню
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_commands
    ))
    
    # Callback для inline-кнопок
    application.add_handler(CallbackQueryHandler(handle_callbacks))
    
    logger.info("=" * 60)
    logger.info("✅ Все handlers зарегистрированы")
    logger.info("🚀 Бот запущен и готов к работе!")
    logger.info("=" * 60)
    
    # Запускаем бота (устойчивый цикл перезапуска при непредвиденных ошибках)
    import time
    try:
        while True:
            try:
                application.run_polling(allowed_updates=Update.ALL_TYPES)
            except Exception as e:
                logger.error(f"run_polling упал: {e}. Перезапуск через 5с")
                time.sleep(5)
                continue
            # Если вышли без исключения — это, скорее всего, внешняя остановка. Дадим шанс авто‑рестарту.
            logger.warning("run_polling завершился. Перезапуск через 5с")
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("⏹ Остановка бота...")
    finally:
        close_connection_pool()
        logger.info("👋 Бот остановлен")


if __name__ == '__main__':
    main()

# bot.py - упрощённая версия для старта

import os
import logging
from threading import Thread
from flask import Flask

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from database.models import init_database, is_user_registered, create_user, is_user_admin
from handlers.registration import get_registration_handler
from handlers.checkin import request_checkin_location, checkout, handle_checkin_location
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
    return "Campus Check-in Bot v2 is running! ✅"

@app.route('/health')
def health():
    return {"status": "ok", "version": "2.0"}

def run_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)


async def start(update: Update, context):
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    # Создаём пользователя если новый
    create_user(user_id, user.username or "Без username", user.full_name)
    
    # Проверяем регистрацию
    if not is_user_registered(user_id):
        # Перенаправляем на регистрацию через ConversationHandler
        return
    
    # Проверяем, админ ли
    is_admin = is_user_admin(user_id)
    
    await update.message.reply_text(
        f"👋 Добро пожаловать, {user.first_name}!\n\n"
        f"Используйте меню для работы с ботом.",
        reply_markup=get_main_keyboard(is_admin)
    )


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
        from handlers.user_menu import show_my_status
        await show_my_status(update, context)
    
    elif text == "👥 Кто в кампусе":
        from handlers.user_menu import show_who_inside
        await show_who_inside(update, context)
    
    elif text == "👤 Все участники":
        from handlers.user_menu import show_all_participants
        await show_all_participants(update, context)
    
    elif text == "⚙️ Настройки":
        from handlers.user_menu import show_settings
        await show_settings(update, context)
    
    elif text == "🔧 Админ-панель" and is_admin:
        from handlers.admin_panel import show_admin_panel
        await show_admin_panel(update, context)
    
    elif text == "❓ Помощь":
        await help_command(update, context)


async def help_command(update: Update, context):
    """Справка"""
    help_text = """
❓ Справка по использованию бота

📍 Я в кампусе - Отметиться с геолокацией
🚪 Я ухожу - Отметить уход
👥 Кто в кампусе - Список присутствующих
👤 Все участники - Все с индикаторами
📊 Мой статус - Ваша информация
📚 База знаний - Материалы
⚙️ Настройки - Управление профилем

💡 Для check-in необходимо находиться в пределах 300м от кампуса!
    """
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())


def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return
    
    # Инициализация БД
    try:
        init_database()
        
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
            logger.info(f"Добавлено {len(ADMIN_IDS)} администраторов")
        
    except Exception as e:
        logger.error(f"Ошибка инициализации: {e}")
        return
    
    # Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask запущен для Render")
    
    # Telegram Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация (ConversationHandler)
    application.add_handler(get_registration_handler())
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработка геолокации
    application.add_handler(MessageHandler(filters.LOCATION, handle_checkin_location))
    
    # Текстовые команды из меню
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_commands
    ))
    
    # Callback для inline-кнопок
    # application.add_handler(CallbackQueryHandler(handle_callbacks))
    
    logger.info("✅ Campus Check-in Bot v2 запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

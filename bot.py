# ============================================
# FILE 1: bot.py (основной файл бота)
# ============================================

import os
import logging
from datetime import datetime, timezone, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from geopy.distance import geodesic
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from threading import Thread
from flask import Flask

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask веб-сервер для Render (чтобы видел открытый порт)
app = Flask(__name__)

@app.route('/')
def home():
    return "Campus Presence Bot is running! ✅"

@app.route('/health')
def health():
    return {"status": "ok", "bot": "running"}

def run_flask():
    """Запуск Flask в отдельном потоке"""
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Конфигурация из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CAMPUS_LATITUDE = float(os.getenv("CAMPUS_LATITUDE", "43.2220"))
CAMPUS_LONGITUDE = float(os.getenv("CAMPUS_LONGITUDE", "76.8512"))
PROXIMITY_RADIUS = int(os.getenv("PROXIMITY_RADIUS", "500"))

# Часовой пояс (UTC+5 для Алматы, UTC+6 для Астаны)
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "5"))  # Алматы UTC+5
TIMEZONE = timezone(timedelta(hours=TIMEZONE_OFFSET))

def get_local_time():
    """Получить текущее локальное время с учётом часового пояса"""
    return datetime.now(TIMEZONE)

@contextmanager
def get_db():
    """Контекстный менеджер для работы с PostgreSQL"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Инициализация базы данных PostgreSQL"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                group_department TEXT,
                geo_consent BOOLEAN DEFAULT FALSE,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица присутствия
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS presence (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                check_in_time TIMESTAMP,
                check_out_time TIMESTAMP,
                date DATE,
                status TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Таблица геолокации
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS geolocation (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                latitude REAL,
                longitude REAL,
                distance_to_campus REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_near_campus BOOLEAN,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        conn.commit()
        logger.info("База данных PostgreSQL инициализирована")

def get_main_keyboard():
    """Главная клавиатура"""
    keyboard = [
        [KeyboardButton("📍 Я в кампусе"), KeyboardButton("🚪 Я ухожу")],
        [KeyboardButton("👥 Кто в кампусе"), KeyboardButton("📊 Мой статус")],
        [KeyboardButton("📍 Отправить геолокацию", request_location=True)],
        [KeyboardButton("⚙️ Настройки"), KeyboardButton("❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    username = user.username or "Без username"
    full_name = user.full_name or "Не указано"
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, full_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        ''', (user_id, username, full_name))
        conn.commit()
    
    welcome_text = f"""
👋 Привет, {full_name}!

Добро пожаловать в Campus Presence Bot!

Я помогу отслеживать ваше присутствие в кампусе.

🔹 Основные функции:
• Отметка прихода/ухода из кампуса
• Просмотр списка присутствующих
• Отслеживание близости к кампусу (опционально)

⚠️ Важно: Геолокация работает через:
📱 Мобильное приложение Telegram
🌐 Веб-версию web.telegram.org
❌ Desktop версия НЕ поддерживает отправку геолокации

Используйте кнопки меню для работы с ботом.
    """
    
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def check_in(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отметка прихода в кампус"""
    user_id = update.effective_user.id
    now = get_local_time()
    today = now.date()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Проверяем, не отмечен ли уже пользователь
        cursor.execute('''
            SELECT * FROM presence 
            WHERE user_id = %s AND date = %s AND status = 'in_campus'
        ''', (user_id, today))
        
        if cursor.fetchone():
            await update.message.reply_text(
                "✅ Вы уже отмечены как находящийся в кампусе!",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Отмечаем приход
        cursor.execute('''
            INSERT INTO presence (user_id, check_in_time, date, status)
            VALUES (%s, %s, %s, 'in_campus')
        ''', (user_id, now, today))
        conn.commit()
    
    await update.message.reply_text(
        f"✅ Вы отмечены в кампусе!\n🕐 Время: {now.strftime('%H:%M')}",
        reply_markup=get_main_keyboard()
    )

async def check_out(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отметка ухода из кампуса"""
    user_id = update.effective_user.id
    now = get_local_time()
    today = now.date()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Находим активную отметку
        cursor.execute('''
            SELECT id FROM presence 
            WHERE user_id = %s AND date = %s AND status = 'in_campus'
            ORDER BY check_in_time DESC LIMIT 1
        ''', (user_id, today))
        
        record = cursor.fetchone()
        
        if not record:
            await update.message.reply_text(
                "❌ Вы не отмечены в кампусе!",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Обновляем отметку
        cursor.execute('''
            UPDATE presence 
            SET check_out_time = %s, status = 'left'
            WHERE id = %s
        ''', (now, record['id']))
        conn.commit()
    
    await update.message.reply_text(
        f"👋 Вы отметились как ушедший!\n🕐 Время: {now.strftime('%H:%M')}",
        reply_markup=get_main_keyboard()
    )

async def who_inside(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список присутствующих"""
    today = get_local_time().date()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем всех присутствующих
        cursor.execute('''
            SELECT u.username, u.full_name, u.group_department, p.check_in_time, g.is_near_campus, g.distance_to_campus
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
    
    # Формируем список
    text = f"👥 В кампусе сейчас: {len(people)} чел.\n\n"
    
    for person in people:
        username = person['username']
        full_name = person['full_name']
        group = person['group_department']
        check_in = person['check_in_time']
        is_near = person['is_near_campus']
        distance = person['distance_to_campus']
        
        # Конвертируем время в локальный часовой пояс
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=timezone.utc)
        local_check_in = check_in.astimezone(TIMEZONE)
        check_in_time = local_check_in.strftime('%H:%M')
        
        status_icon = "🟢"
        status_text = ""
        
        if is_near is not None:
            if is_near:
                status_icon = "🟡"
                status_text = f" - Рядом ({int(distance)}м)"
        
        group_text = f" ({group})" if group else ""
        
        text += f"{status_icon} @{username} - {full_name}{group_text}{status_text}\n"
        text += f"   └ С {check_in_time}\n\n"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать мой статус"""
    user_id = update.effective_user.id
    today = get_local_time().date()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Проверяем статус присутствия
        cursor.execute('''
            SELECT check_in_time, check_out_time, status
            FROM presence
            WHERE user_id = %s AND date = %s
            ORDER BY check_in_time DESC LIMIT 1
        ''', (user_id, today))
        
        presence = cursor.fetchone()
        
        # Получаем геолокацию
        cursor.execute('''
            SELECT latitude, longitude, distance_to_campus, is_near_campus, timestamp
            FROM geolocation
            WHERE user_id = %s
            ORDER BY timestamp DESC LIMIT 1
        ''', (user_id,))
        
        geo = cursor.fetchone()
        
        # Проверяем согласие на геоданные
        cursor.execute('SELECT geo_consent FROM users WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        geo_consent = result['geo_consent'] if result else False
    
    text = "📊 Ваш статус:\n\n"
    
    if presence:
        status = presence['status']
        if status == 'in_campus':
            check_in = presence['check_in_time']
            # Конвертируем время в локальный часовой пояс
            if check_in.tzinfo is None:
                check_in = check_in.replace(tzinfo=timezone.utc)
            local_check_in = check_in.astimezone(TIMEZONE)
            check_in_str = local_check_in.strftime('%H:%M')
            text += f"🟢 Статус: В кампусе\n"
            text += f"🕐 Пришли в: {check_in_str}\n"
        else:
            text += f"⚪ Статус: Вне кампуса\n"
    else:
        text += f"⚪ Статус: Сегодня не отмечались\n"
    
    text += f"\n📍 Геолокация: {'✅ Включена' if geo_consent else '❌ Отключена'}\n"
    
    if geo and geo_consent:
        distance = int(geo['distance_to_campus'])
        is_near = geo['is_near_campus']
        last_update = geo['timestamp']
        
        # Конвертируем время в локальный часовой пояс
        if last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=timezone.utc)
        local_update = last_update.astimezone(TIMEZONE)
        last_update_str = local_update.strftime('%H:%M')
        
        if is_near:
            text += f"🟡 Вы рядом с кампусом ({distance}м)\n"
        else:
            text += f"📍 Расстояние до кампуса: {distance}м\n"
        
        text += f"🕐 Последнее обновление: {last_update_str}\n"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройки пользователя"""
    user_id = update.effective_user.id
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT geo_consent, full_name, group_department FROM users WHERE user_id = %s', (user_id,))
        user_data = cursor.fetchone()
        geo_consent = user_data['geo_consent']
        full_name = user_data['full_name']
        group_department = user_data['group_department'] or "Не указано"
    
    keyboard = [
        [InlineKeyboardButton(
            f"📍 Геолокация: {'✅ Вкл' if geo_consent else '❌ Выкл'}", 
            callback_data='toggle_geo'
        )],
        [InlineKeyboardButton("✏️ Изменить имя", callback_data='edit_name')],
        [InlineKeyboardButton("🏢 Изменить группу/отдел", callback_data='edit_group')],
        [InlineKeyboardButton("ℹ️ О геолокации", callback_data='geo_info')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
⚙️ Настройки

👤 Имя: {full_name}
🏢 Группа/Отдел: {group_department}
📍 Геолокация: {'✅ Включена' if geo_consent else '❌ Отключена'}

📱 Для отправки геолокации используйте:
• Мобильное приложение Telegram
• Веб-версию (web.telegram.org)
• Telegram Desktop не поддерживает отправку геолокации

Геолокация опциональна - бот работает и без неё!
    """
    
    await update.message.reply_text(text, reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на inline кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'toggle_geo':
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT geo_consent FROM users WHERE user_id = %s', (user_id,))
            current = cursor.fetchone()['geo_consent']
            new_value = not current
            
            cursor.execute('UPDATE users SET geo_consent = %s WHERE user_id = %s', (new_value, user_id))
            conn.commit()
        
        status_text = "включена ✅" if new_value else "отключена ❌"
        
        keyboard = [
            [InlineKeyboardButton(
                f"📍 Геолокация: {'✅ Вкл' if new_value else '❌ Выкл'}", 
                callback_data='toggle_geo'
            )],
            [InlineKeyboardButton("✏️ Изменить имя", callback_data='edit_name')],
            [InlineKeyboardButton("🏢 Изменить группу/отдел", callback_data='edit_group')],
            [InlineKeyboardButton("ℹ️ О геолокации", callback_data='geo_info')]
        ]
        
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        
        extra_msg = ""
        if new_value:
            extra_msg = "\n\n📱 Отправьте геолокацию через:\n• Мобильное приложение Telegram\n• Веб-версию web.telegram.org\n(Desktop не поддерживает геолокацию)"
        
        await query.message.reply_text(
            f"📍 Геолокация {status_text}{extra_msg}",
            reply_markup=get_main_keyboard()
        )
    
    elif query.data == 'geo_info':
        info_text = """
ℹ️ О функции геолокации

Когда вы включаете геолокацию и отправляете свое местоположение:

• Бот рассчитывает расстояние до кампуса
• Если вы в пределах 500м, показывается статус "Рядом"
• Другие пользователи видят, что вы близко к кампусу
• Ваши точные координаты НЕ показываются другим

📱 Для отправки геолокации:
• Откройте Telegram на смартфоне
• Или используйте web.telegram.org в браузере
• Desktop версия НЕ поддерживает отправку геолокации

⚠️ Геолокация опциональна - основные функции бота работают без неё!

Вы можете отключить эту функцию в любой момент.
        """
        await query.message.reply_text(info_text)
    
    elif query.data == 'edit_name':
        await query.message.reply_text(
            "✏️ Отправьте ваше новое имя:",
            reply_markup=get_main_keyboard()
        )
        context.user_data['editing'] = 'name'
    
    elif query.data == 'edit_group':
        await query.message.reply_text(
            "🏢 Отправьте вашу группу или отдел:",
            reply_markup=get_main_keyboard()
        )
        context.user_data['editing'] = 'group'

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученной геолокации"""
    user_id = update.effective_user.id
    location = update.message.location
    
    # Проверяем согласие
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT geo_consent FROM users WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        geo_consent = result['geo_consent'] if result else False
        
        if not geo_consent:
            await update.message.reply_text(
                "❌ Сначала включите геолокацию в настройках!",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Рассчитываем расстояние
        user_coords = (location.latitude, location.longitude)
        campus_coords = (CAMPUS_LATITUDE, CAMPUS_LONGITUDE)
        distance = geodesic(user_coords, campus_coords).meters
        is_near = distance <= PROXIMITY_RADIUS
        
        # Сохраняем в БД
        cursor.execute('''
            INSERT INTO geolocation (user_id, latitude, longitude, distance_to_campus, is_near_campus)
            VALUES (%s, %s, %s, %s, %s)
        ''', (user_id, location.latitude, location.longitude, distance, is_near))
        conn.commit()
    
    status_text = f"🟡 Вы рядом с кампусом! ({int(distance)}м)" if is_near else f"📍 Расстояние до кампуса: {int(distance)}м"
    
    await update.message.reply_text(
        f"✅ Геолокация обновлена!\n{status_text}",
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам"""
    help_text = """
❓ Справка по использованию бота

📍 Я в кампусе - Отметить приход
🚪 Я ухожу - Отметить уход
👥 Кто в кампусе - Список присутствующих
📊 Мой статус - Ваш текущий статус
📍 Отправить геолокацию - Обновить местоположение
⚙️ Настройки - Управление разрешениями

Команды:
/start - Начать работу
/checkin - Отметиться в кампусе
/checkout - Отметить уход
/whosinside - Список присутствующих
/mystatus - Мой статус
/settings - Настройки
/help - Эта справка

💡 Совет: Включите геолокацию в настройках, чтобы другие видели, когда вы рядом с кампусом!
    """
    
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых кнопок"""
    text = update.message.text
    user_id = update.effective_user.id
    
    # Проверяем, идет ли редактирование профиля
    if context.user_data.get('editing'):
        editing = context.user_data['editing']
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            if editing == 'name':
                cursor.execute('UPDATE users SET full_name = %s WHERE user_id = %s', (text, user_id))
                conn.commit()
                await update.message.reply_text(
                    f"✅ Имя обновлено: {text}",
                    reply_markup=get_main_keyboard()
                )
            elif editing == 'group':
                cursor.execute('UPDATE users SET group_department = %s WHERE user_id = %s', (text, user_id))
                conn.commit()
                await update.message.reply_text(
                    f"✅ Группа/отдел обновлена: {text}",
                    reply_markup=get_main_keyboard()
                )
        
        context.user_data['editing'] = None
        return
    
    # Обработка кнопок меню
    if text == "📍 Я в кампусе":
        await check_in(update, context)
    elif text == "🚪 Я ухожу":
        await check_out(update, context)
    elif text == "👥 Кто в кампусе":
        await who_inside(update, context)
    elif text == "📊 Мой статус":
        await my_status(update, context)
    elif text == "⚙️ Настройки":
        await settings(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)

def main():
    """Запуск бота"""
    # Проверяем наличие токена
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return
    
    if not DATABASE_URL:
        logger.error("DATABASE_URL не установлен!")
        return
    
    # Инициализация БД
    try:
        init_db()
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        return
    
    # Запускаем Flask в отдельном потоке (для Render)
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask веб-сервер запущен для Render")
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("checkin", check_in))
    application.add_handler(CommandHandler("checkout", check_out))
    application.add_handler(CommandHandler("whosinside", who_inside))
    application.add_handler(CommandHandler("mystatus", my_status))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    
    # Обработчик callback
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Запускаем бота
    logger.info("Бот запущен на Render.com!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()


# ============================================
# FILE 2: requirements.txt
# ============================================

"""
python-telegram-bot==20.7
geopy==2.4.1
psycopg2-binary==2.9.10
Flask==3.0.0
"""


# ============================================
# FILE 3: runtime.txt (ВАЖНО для Python 3.13)
# ============================================

"""
python-3.11.9
"""


# ============================================
# FILE 3: render.yaml (опционально)
# ============================================

"""
services:
  - type: web
    name: campus-presence-bot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python bot.py
    envVars:
      - key: BOT_TOKEN
        sync: false
      - key: DATABASE_URL
        fromDatabase:
          name: campus-bot-db
          property: connectionString
      - key: CAMPUS_LATITUDE
        value: "43.2220"
      - key: CAMPUS_LONGITUDE
        value: "76.8512"
      - key: PROXIMITY_RADIUS
        value: "500"

databases:
  - name: campus-bot-db
    databaseName: campus_bot
    user: campus_bot_user
"""

import os
import logging
from datetime import datetime, time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from geopy.distance import geodesic
import sqlite3
from contextlib import contextmanager

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация (замените на свои значения)
BOT_TOKEN = "8567193777:AAFhpxhnQjVhWOjAhHdw0_liDdjbnAncr9s"  # Получите токен у @BotFather
CAMPUS_LATITUDE = 43.239581  # Координаты кампуса (пример: Алматы)
CAMPUS_LONGITUDE = 76.962465
PROXIMITY_RADIUS = 500  # метров

# База данных
DB_NAME = "campus_bot.db"


@contextmanager
def get_db():
    """Контекстный менеджер для работы с БД"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Инициализация базы данных"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Таблица пользователей
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS users
                       (
                           user_id
                           INTEGER
                           PRIMARY
                           KEY,
                           username
                           TEXT,
                           full_name
                           TEXT,
                           group_department
                           TEXT,
                           geo_consent
                           BOOLEAN
                           DEFAULT
                           0,
                           registration_date
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP,
                           last_update
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )
                       ''')

        # Таблица присутствия
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS presence
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           user_id
                           INTEGER,
                           check_in_time
                           TIMESTAMP,
                           check_out_time
                           TIMESTAMP,
                           date
                           DATE,
                           status
                           TEXT,
                           FOREIGN
                           KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           user_id
                       )
                           )
                       ''')

        # Таблица геолокации
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS geolocation
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           user_id
                           INTEGER,
                           latitude
                           REAL,
                           longitude
                           REAL,
                           distance_to_campus
                           REAL,
                           timestamp
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP,
                           is_near_campus
                           BOOLEAN,
                           FOREIGN
                           KEY
                       (
                           user_id
                       ) REFERENCES users
                       (
                           user_id
                       )
                           )
                       ''')

        conn.commit()
        logger.info("База данных инициализирована")


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
                       INSERT
                       OR IGNORE INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
                       ''', (user_id, username, full_name))
        conn.commit()

    welcome_text = f"""
👋 Привет, {full_name}!

Добро пожаловать в Campus Presence Bot!

Я помогу отслеживать ваше присутствие в кампусе.

🔹 Основные функции:
• Отметка прихода/ухода из кампуса
• Просмотр списка присутствующих
• Отслеживание близости к кампусу (с вашего согласия)

Используйте кнопки меню для работы с ботом.
    """

    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())


async def check_in(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отметка прихода в кампус"""
    user_id = update.effective_user.id
    now = datetime.now()
    today = now.date()

    with get_db() as conn:
        cursor = conn.cursor()

        # Проверяем, не отмечен ли уже пользователь
        cursor.execute('''
                       SELECT *
                       FROM presence
                       WHERE user_id = ? AND date = ? AND status = 'in_campus'
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
                       VALUES (?, ?, ?, 'in_campus')
                       ''', (user_id, now, today))
        conn.commit()

    await update.message.reply_text(
        f"✅ Вы отмечены в кампусе!\n🕐 Время: {now.strftime('%H:%M')}",
        reply_markup=get_main_keyboard()
    )


async def check_out(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отметка ухода из кампуса"""
    user_id = update.effective_user.id
    now = datetime.now()
    today = now.date()

    with get_db() as conn:
        cursor = conn.cursor()

        # Находим активную отметку
        cursor.execute('''
                       SELECT id
                       FROM presence
                       WHERE user_id = ? AND date = ? AND status = 'in_campus'
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
                       SET check_out_time = ?,
                           status         = 'left'
                       WHERE id = ?
                       ''', (now, record[0]))
        conn.commit()

    await update.message.reply_text(
        f"👋 Вы отметились как ушедший!\n🕐 Время: {now.strftime('%H:%M')}",
        reply_markup=get_main_keyboard()
    )


async def who_inside(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список присутствующих"""
    today = datetime.now().date()

    with get_db() as conn:
        cursor = conn.cursor()

        # Получаем всех присутствующих
        cursor.execute('''
                       SELECT u.username, u.full_name, p.check_in_time, g.is_near_campus, g.distance_to_campus
                       FROM presence p
                                JOIN users u ON p.user_id = u.user_id
                                LEFT JOIN (SELECT user_id, is_near_campus, distance_to_campus
                                           FROM geolocation
                                           WHERE id IN (SELECT MAX(id)
                                                        FROM geolocation
                                                        GROUP BY user_id)) g ON u.user_id = g.user_id
                       WHERE p.date = ?
                         AND p.status = 'in_campus'
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
        username, full_name, check_in, is_near, distance = person
        check_in_time = datetime.fromisoformat(check_in).strftime('%H:%M')

        status_icon = "🟢"
        status_text = ""

        if is_near is not None:
            if is_near:
                status_icon = "🟡"
                status_text = f" - Рядом ({int(distance)}м)"

        text += f"{status_icon} @{username} ({full_name}){status_text}\n"
        text += f"   └ С {check_in_time}\n\n"

    await update.message.reply_text(text, reply_markup=get_main_keyboard())


async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать мой статус"""
    user_id = update.effective_user.id
    today = datetime.now().date()

    with get_db() as conn:
        cursor = conn.cursor()

        # Проверяем статус присутствия
        cursor.execute('''
                       SELECT check_in_time, check_out_time, status
                       FROM presence
                       WHERE user_id = ? AND date = ?
                       ORDER BY check_in_time DESC LIMIT 1
                       ''', (user_id, today))

        presence = cursor.fetchone()

        # Получаем геолокацию
        cursor.execute('''
                       SELECT latitude, longitude, distance_to_campus, is_near_campus, timestamp
                       FROM geolocation
                       WHERE user_id = ?
                       ORDER BY timestamp DESC LIMIT 1
                       ''', (user_id,))

        geo = cursor.fetchone()

        # Проверяем согласие на геоданные
        cursor.execute('SELECT geo_consent FROM users WHERE user_id = ?', (user_id,))
        geo_consent = cursor.fetchone()[0]

    text = "📊 Ваш статус:\n\n"

    if presence:
        status = presence[2]
        if status == 'in_campus':
            check_in = datetime.fromisoformat(presence[0]).strftime('%H:%M')
            text += f"🟢 Статус: В кампусе\n"
            text += f"🕐 Пришли в: {check_in}\n"
        else:
            text += f"⚪ Статус: Вне кампуса\n"
    else:
        text += f"⚪ Статус: Сегодня не отмечались\n"

    text += f"\n📍 Геолокация: {'✅ Включена' if geo_consent else '❌ Отключена'}\n"

    if geo and geo_consent:
        distance = int(geo[2])
        is_near = geo[3]
        last_update = datetime.fromisoformat(geo[4]).strftime('%H:%M')

        if is_near:
            text += f"🟡 Вы рядом с кампусом ({distance}м)\n"
        else:
            text += f"📍 Расстояние до кампуса: {distance}м\n"

        text += f"🕐 Последнее обновление: {last_update}\n"

    await update.message.reply_text(text, reply_markup=get_main_keyboard())


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Настройки пользователя"""
    user_id = update.effective_user.id

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT geo_consent FROM users WHERE user_id = ?', (user_id,))
        geo_consent = cursor.fetchone()[0]

    keyboard = [
        [InlineKeyboardButton(
            f"📍 Геолокация: {'✅ Вкл' if geo_consent else '❌ Выкл'}",
            callback_data='toggle_geo'
        )],
        [InlineKeyboardButton("ℹ️ О геолокации", callback_data='geo_info')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = """
⚙️ Настройки

Управляйте вашими данными и разрешениями.

📍 Геолокация:
Позволяет боту отслеживать ваше расстояние до кампуса и показывать статус "Рядом с кампусом" другим пользователям.
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
            cursor.execute('SELECT geo_consent FROM users WHERE user_id = ?', (user_id,))
            current = cursor.fetchone()[0]
            new_value = not current

            cursor.execute('UPDATE users SET geo_consent = ? WHERE user_id = ?', (new_value, user_id))
            conn.commit()

        status_text = "включена ✅" if new_value else "отключена ❌"

        keyboard = [
            [InlineKeyboardButton(
                f"📍 Геолокация: {'✅ Вкл' if new_value else '❌ Выкл'}",
                callback_data='toggle_geo'
            )],
            [InlineKeyboardButton("ℹ️ О геолокации", callback_data='geo_info')]
        ]

        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        await query.message.reply_text(
            f"📍 Геолокация {status_text}\n\n" +
            ("Теперь отправьте вашу геолокацию через кнопку в меню." if new_value else ""),
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

Вы можете отключить эту функцию в любой момент.
        """
        await query.message.reply_text(info_text)


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка полученной геолокации"""
    user_id = update.effective_user.id
    location = update.message.location

    # Проверяем согласие
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT geo_consent FROM users WHERE user_id = ?', (user_id,))
        geo_consent = cursor.fetchone()[0]

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
                       VALUES (?, ?, ?, ?, ?)
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
    # Инициализация БД
    init_db()

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
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

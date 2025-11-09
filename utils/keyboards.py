# ============================================
# FILE: utils/keyboards.py
# ============================================

from telegram import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup


def get_main_keyboard(is_admin=False):
    """Главная клавиатура для зарегистрированных пользователей"""
    keyboard = [
        [KeyboardButton("📍 Я в кампусе"), KeyboardButton("🚪 Я ухожу")],
        [KeyboardButton("👥 Кто в кампусе"), KeyboardButton("👤 Все участники")],
        [KeyboardButton("📊 Мой статус"), KeyboardButton("📚 База знаний")],
    ]
    
    if is_admin:
        keyboard.append([KeyboardButton("⚙️ Настройки"), KeyboardButton("🔧 Админ-панель")])
    else:
        keyboard.append([KeyboardButton("⚙️ Настройки"), KeyboardButton("❓ Помощь")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_keyboard():
    """Клавиатура админ-панели"""
    keyboard = [
        [InlineKeyboardButton("👥 Мониторинг присутствия", callback_data='admin_monitoring')],
        [InlineKeyboardButton("👤 Все зарегистрированные", callback_data='admin_all_users')],
        [InlineKeyboardButton("📋 Архив мероприятий", callback_data='admin_events_archive')],
        [InlineKeyboardButton("📢 Создать пост", callback_data='admin_create_post')],
        [InlineKeyboardButton("🎯 Создать мероприятие", callback_data='admin_create_event')],
        [InlineKeyboardButton("📚 Загрузить в Базу Знаний", callback_data='admin_upload_kb')],
        [InlineKeyboardButton("📊 Экспорт данных", callback_data='admin_export_data')],
        [InlineKeyboardButton("📸 Конкурс фото", callback_data='admin_photo_contest')],
        [InlineKeyboardButton("◀️ Назад", callback_data='admin_close')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_settings_keyboard(geo_consent=False):
    """Клавиатура настроек"""
    keyboard = [
        [InlineKeyboardButton(
            f"📍 Геолокация: {'✅ Вкл' if geo_consent else '❌ Выкл'}", 
            callback_data='toggle_geo'
        )],
        [InlineKeyboardButton("✏️ Редактировать профиль", callback_data='edit_profile')],
        [InlineKeyboardButton("📊 Моя статистика", callback_data='my_stats')],
        [InlineKeyboardButton("◀️ Назад", callback_data='settings_close')]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_export_keyboard():
    """Клавиатура экспорта данных"""
    keyboard = [
        [InlineKeyboardButton("📅 За сегодня", callback_data='export_today')],
        [InlineKeyboardButton("📅 За неделю", callback_data='export_week')],
        [InlineKeyboardButton("📅 За месяц", callback_data='export_month')],
        [InlineKeyboardButton("🎯 По мероприятию", callback_data='export_event')],
        [InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]
    ]
    return InlineKeyboardMarkup(keyboard)

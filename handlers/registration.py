# ============================================
# FILE: handlers/registration.py
# ============================================

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime
import re
import logging

from config import States
from database.models import is_user_registered, complete_registration
from utils.keyboards import get_main_keyboard

logger = logging.getLogger(__name__)


async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса регистрации"""
    welcome_text = """
👋 Добро пожаловать в Campus Check-in Bot!

Для использования бота необходимо пройти регистрацию.

📝 Мы запросим следующую информацию:
• Имя
• Фамилия
• Дата рождения
• Команда/Роль
• Номер телефона

Давайте начнём! Введите ваше **имя**:
    """
    
    await update.message.reply_text(welcome_text, reply_markup=ReplyKeyboardRemove())
    return States.REGISTRATION_FIRST_NAME


async def registration_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение имени"""
    first_name = update.message.text.strip()
    
    if len(first_name) < 2:
        await update.message.reply_text("❌ Имя должно содержать минимум 2 символа. Попробуйте снова:")
        return States.REGISTRATION_FIRST_NAME
    
    context.user_data['registration'] = {'first_name': first_name}
    
    await update.message.reply_text(f"✅ Имя: {first_name}\n\nТеперь введите вашу **фамилию**:")
    return States.REGISTRATION_LAST_NAME


async def registration_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение фамилии"""
    last_name = update.message.text.strip()
    
    if len(last_name) < 2:
        await update.message.reply_text("❌ Фамилия должна содержать минимум 2 символа. Попробуйте снова:")
        return States.REGISTRATION_LAST_NAME
    
    context.user_data['registration']['last_name'] = last_name
    
    await update.message.reply_text(
        f"✅ Фамилия: {last_name}\n\n"
        "Введите вашу **дату рождения** в формате ДД.ММ.ГГГГ\n"
        "Например: 15.03.2000"
    )
    return States.REGISTRATION_BIRTH_DATE


async def registration_birth_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение даты рождения"""
    birth_date_str = update.message.text.strip()
    
    # Проверка формата ДД.ММ.ГГГГ
    pattern = r'^\d{2}\.\d{2}\.\d{4}$'
    if not re.match(pattern, birth_date_str):
        await update.message.reply_text(
            "❌ Неверный формат даты!\n"
            "Используйте формат ДД.ММ.ГГГГ (например: 15.03.2000)"
        )
        return States.REGISTRATION_BIRTH_DATE
    
    try:
        birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y').date()
        
        # Проверка возраста (от 14 до 100 лет)
        age = (datetime.now().date() - birth_date).days // 365
        if age < 14 or age > 100:
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректную дату рождения."
            )
            return States.REGISTRATION_BIRTH_DATE
        
    except ValueError:
        await update.message.reply_text(
            "❌ Некорректная дата! Попробуйте снова (ДД.ММ.ГГГГ):"
        )
        return States.REGISTRATION_BIRTH_DATE
    
    context.user_data['registration']['birth_date'] = birth_date
    
    await update.message.reply_text(
        f"✅ Дата рождения: {birth_date_str}\n\n"
        "Введите вашу **команду или роль**:\n"
        "Например: Идеолог, Реформатор, Организатор и т.д."
    )
    return States.REGISTRATION_TEAM_ROLE


async def registration_team_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение команды/роли"""
    team_role = update.message.text.strip()
    
    if len(team_role) < 2:
        await update.message.reply_text("❌ Команда/роль должна содержать минимум 2 символа. Попробуйте снова:")
        return States.REGISTRATION_TEAM_ROLE
    
    context.user_data['registration']['team_role'] = team_role
    
    # Создаём кнопку для отправки номера телефона
    keyboard = [[KeyboardButton("📱 Отправить номер телефона", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"✅ Команда/Роль: {team_role}\n\n"
        "Последний шаг! Отправьте ваш **номер телефона**:\n\n"
        "Используйте кнопку ниже или введите вручную в формате:\n"
        "+7 700 123 45 67",
        reply_markup=reply_markup
    )
    return States.REGISTRATION_PHONE


async def registration_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение номера телефона"""
    # Проверяем, отправлен ли контакт через кнопку
    if update.message.contact:
        phone_number = update.message.contact.phone_number
    else:
        phone_text = update.message.text.strip()
        
        # Валидация номера телефона (простая проверка)
        phone_pattern = r'^\+?[0-9\s\-\(\)]{10,20}$'
        if not re.match(phone_pattern, phone_text):
            await update.message.reply_text(
                "❌ Неверный формат номера телефона!\n"
                "Используйте кнопку или введите в формате: +7 700 123 45 67"
            )
            return States.REGISTRATION_PHONE
        
        phone_number = phone_text
    
    context.user_data['registration']['phone_number'] = phone_number
    
    # Сохраняем данные в БД
    user_id = update.effective_user.id
    registration_data = context.user_data['registration']
    
    try:
        complete_registration(user_id, registration_data)
        
        # Формируем итоговое сообщение
        summary = f"""
✅ **Регистрация завершена успешно!**

📋 Ваши данные:
👤 Имя: {registration_data['first_name']}
👤 Фамилия: {registration_data['last_name']}
🎂 Дата рождения: {registration_data['birth_date'].strftime('%d.%m.%Y')}
👥 Команда/Роль: {registration_data['team_role']}
📱 Телефон: {phone_number}

Теперь вы можете пользоваться всеми функциями бота! 🎉

📍 Для отметки в кампусе нажмите "Я в кампусе" и отправьте вашу геолокацию.
        """

        from database.models import is_user_admin
        is_admin = is_user_admin(user_id)
        await update.message.reply_text(
            summary,
            reply_markup=get_main_keyboard(is_admin)
        )
        
        # Очищаем данные регистрации
        context.user_data.clear()
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении регистрации: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при сохранении данных. Попробуйте позже или обратитесь к администратору."
        )
        return ConversationHandler.END


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена регистрации"""
    await update.message.reply_text(
        "❌ Регистрация отменена.\n\n"
        "Для использования бота необходимо пройти регистрацию.\n"
        "Отправьте /start для повторной попытки.",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END


def get_registration_handler():
    """Возвращает ConversationHandler для регистрации"""
    from telegram.ext import CommandHandler, MessageHandler, filters
    
    return ConversationHandler(
        entry_points=[CommandHandler('start', start_registration)],
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
        name="registration",
        persistent=False
    )

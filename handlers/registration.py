from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from config import States
from database.db_manager import get_connection

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите ваше имя:")
    return States.REG_FIRST_NAME

async def get_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["first_name"] = update.message.text
    await update.message.reply_text("Введите фамилию:")
    return States.REG_LAST_NAME

async def get_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["last_name"] = update.message.text
    await update.message.reply_text("Введите дату рождения (ГГГГ-ММ-ДД):")
    return States.REG_BIRTH_DATE

async def get_birth_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["birth_date"] = update.message.text
    await update.message.reply_text("Введите вашу роль (например, студент):")
    return States.REG_ROLE

async def get_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["role"] = update.message.text
    await update.message.reply_text("Введите номер телефона:")
    return States.REG_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (telegram_id, first_name, last_name, birth_date, role, phone)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (telegram_id) DO NOTHING
    """, (update.effective_user.id, data["first_name"], data["last_name"], data["birth_date"], data["role"], update.message.text))
    conn.commit()
    cur.close()
    conn.close()

    await update.message.reply_text("✅ Регистрация завершена!")
    return ConversationHandler.END


# ============================================
# FILE: utils/decorators.py
# ============================================

from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import logging

from database.models import is_user_registered, is_user_admin
from utils.keyboards import get_main_keyboard

logger = logging.getLogger(__name__)


def registered_only(func):
    """Декоратор: доступ только для зарегистрированных пользователей"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        
        if not is_user_registered(user_id):
            await update.message.reply_text(
                "❌ Для использования этой функции необходимо пройти регистрацию.\n\n"
                "Отправьте /start для начала регистрации."
            )
            return
        
        return await func(update, context, *args, **kwargs)
    
    return wrapper


def admin_only(func):
    """Декоратор: доступ только для администраторов"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        
        # Проверяем регистрацию
        if not is_user_registered(user_id):
            await update.message.reply_text(
                "❌ Для использования этой функции необходимо пройти регистрацию.\n\n"
                "Отправьте /start для начала регистрации."
            )
            return
        
        # Проверяем права администратора
        if not is_user_admin(user_id):
            await update.message.reply_text(
                "❌ У вас нет прав администратора.",
                reply_markup=get_main_keyboard()
            )
            return
        
        return await func(update, context, *args, **kwargs)
    
    return wrapper


def admin_callback_only(func):
    """Декоратор для callback-запросов: доступ только для администраторов"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        query = update.callback_query
        user_id = query.from_user.id
        
        if not is_user_admin(user_id):
            await query.answer("❌ У вас нет прав администратора.", show_alert=True)
            return
        
        return await func(update, context, *args, **kwargs)
    
    return wrapper

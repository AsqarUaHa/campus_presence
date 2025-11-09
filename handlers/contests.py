# ============================================
# FILE: handlers/contests.py
# ============================================

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from datetime import datetime, time
import logging

from config import States, TIMEZONE, CONTEST_END_TIME
from database.db_manager import get_db
from utils.keyboards import get_main_keyboard
from utils.decorators import registered_only, admin_callback_only

logger = logging.getLogger(__name__)


def get_local_time():
    """Получить текущее локальное время"""
    return datetime.now(TIMEZONE)


@admin_callback_only
async def start_photo_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск конкурса фото"""
    query = update.callback_query
    await query.answer()
    
    # Объявляем конкурс всем пользователям
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE is_registered = TRUE')
        users = cursor.fetchall()
    
    contest_text = """
📸 **Конкурс "Лучшее фото"**

🎯 Отправьте своё лучшее фото дня!

Условия:
• Одно фото от участника
• Приём до 02:00
• Голосование среди всех участников
• Победитель получит признание! 🏆

Чтобы участвовать, просто отправьте фото в чат с ботом.
    """
    
    bot = context.bot
    sent_count = 0
    
    for user in users:
        try:
            await bot.send_message(
                chat_id=user['user_id'],
                text=contest_text
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о конкурсе: {e}")
    
    await query.message.reply_text(
        f"✅ Конкурс запущен!\n"
        f"📢 Уведомлено участников: {sent_count}"
    )


@registered_only
async def upload_contest_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Загрузка фото на конкурс"""
    if not update.message.photo:
        await update.message.reply_text(
            "❌ Пожалуйста, отправьте фото!",
            reply_markup=get_main_keyboard()
        )
        return
    
    user_id = update.effective_user.id
    photo = update.message.photo[-1]  # Берём самое большое фото
    
    # Проверяем, не загружал ли уже
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id FROM photo_contest
            WHERE user_id = %s AND contest_date = CURRENT_DATE
        ''', (user_id,))
        
        if cursor.fetchone():
            await update.message.reply_text(
                "❌ Вы уже загрузили фото на сегодняшний конкурс!",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Сохраняем фото
        cursor.execute('''
            INSERT INTO photo_contest (user_id, photo_file_id)
            VALUES (%s, %s)
        ''', (user_id, photo.file_id))
        conn.commit()
    
    await update.message.reply_text(
        "✅ Ваше фото принято на конкурс!\n"
        "🗳 Голосование начнётся после окончания приёма фото.",
        reply_markup=get_main_keyboard()
    )


@admin_callback_only
async def view_contest_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр фото конкурса"""
    query = update.callback_query
    await query.answer()
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                pc.id,
                pc.photo_file_id,
                pc.votes,
                u.first_name,
                u.last_name
            FROM photo_contest pc
            JOIN users u ON pc.user_id = u.user_id
            WHERE pc.contest_date = CURRENT_DATE
            ORDER BY pc.votes DESC
        ''')
        photos = cursor.fetchall()
    
    if not photos:
        await query.message.reply_text("📸 Пока нет фото на конкурсе.")
        return
    
    await query.message.reply_text(
        f"📸 Всего фото на конкурсе: {len(photos)}\n\n"
        "Сейчас отправлю все фото..."
    )
    
    for photo in photos:
        caption = f"{photo['first_name']} {photo['last_name']}\n" \
                  f"🗳 Голосов: {photo['votes']}"
        
        await query.message.reply_photo(
            photo=photo['photo_file_id'],
            caption=caption
        )


async def end_photo_contest(context: ContextTypes.DEFAULT_TYPE):
    """Автоматическое завершение конкурса в 02:00"""
    now = get_local_time()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Находим победителя
        cursor.execute('''
            SELECT 
                pc.id,
                pc.photo_file_id,
                pc.votes,
                u.first_name,
                u.last_name,
                u.user_id
            FROM photo_contest pc
            JOIN users u ON pc.user_id = u.user_id
            WHERE pc.contest_date = %s
            ORDER BY pc.votes DESC
            LIMIT 1
        ''', (now.date(),))
        
        winner = cursor.fetchone()
        
        if not winner:
            logger.info("Нет фото на конкурсе сегодня")
            return
        
        # Отмечаем победителя
        cursor.execute('''
            UPDATE photo_contest
            SET is_winner = TRUE
            WHERE id = %s
        ''', (winner['id'],))
        conn.commit()
        
        # Уведомляем всех участников
        cursor.execute('SELECT user_id FROM users WHERE is_registered = TRUE')
        users = cursor.fetchall()
    
    winner_text = f"""
🏆 **Конкурс "Лучшее фото" завершён!**

Победитель: {winner['first_name']} {winner['last_name']}
🗳 Голосов: {winner['votes']}

Поздравляем! 🎉
    """
    
    bot = context.bot
    
    for user in users:
        try:
            await bot.send_photo(
                chat_id=user['user_id'],
                photo=winner['photo_file_id'],
                caption=winner_text
            )
        except Exception as e:
            logger.error(f"Ошибка отправки результатов конкурса: {e}")
    
    logger.info(f"Конкурс завершён. Победитель: {winner['first_name']} {winner['last_name']}")


async def vote_for_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Голосование за фото"""
    query = update.callback_query
    
    if not query.data.startswith('vote_'):
        return
    
    photo_id = int(query.data.replace('vote_', ''))
    voter_id = query.from_user.id
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Проверяем, не голосовал ли уже
        cursor.execute('''
            SELECT id FROM photo_votes
            WHERE photo_id = %s AND voter_id = %s
        ''', (photo_id, voter_id))
        
        if cursor.fetchone():
            await query.answer("❌ Вы уже голосовали за это фото!", show_alert=True)
            return
        
        # Добавляем голос
        cursor.execute('''
            INSERT INTO photo_votes (photo_id, voter_id)
            VALUES (%s, %s)
        ''', (photo_id, voter_id))
        
        # Увеличиваем счётчик
        cursor.execute('''
            UPDATE photo_contest
            SET votes = votes + 1
            WHERE id = %s
        ''', (photo_id,))
        
        conn.commit()
    
    await query.answer("✅ Ваш голос учтён!", show_alert=True)

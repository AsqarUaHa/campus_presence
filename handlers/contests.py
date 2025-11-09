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

🎯 Участвуйте: пришлите одно фото дня с описанием (подписью).

Условия:
• Одно фото от участника
• Приём до 02:00
• Голосование среди всех участников
• Победитель получит признание! 🏆

Нажмите «Участвовать», чтобы отправить фото.
    """
    
    bot = context.bot
    sent_count = 0

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    join_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Участвовать", callback_data='contest_join')],
        [InlineKeyboardButton("❌ Не участвовать", callback_data='contest_decline')]
    ])
    
    for user in users:
        try:
            await bot.send_message(
                chat_id=user['user_id'],
                text=contest_text,
                reply_markup=join_kb
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
    """Загрузка/редактирование фото на конкурс по кнопкам участия"""
    if not update.message.photo:
        await update.message.reply_text("❌ Пожалуйста, отправьте фото (с подписью — это описание).")
        return
    
    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    caption = (update.message.caption or '').strip()
    
    waiting_new = context.user_data.get('contest_waiting_photo')
    editing = context.user_data.get('contest_edit_photo')
    
    # Проверяем, не загружал ли уже
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id FROM photo_contest
            WHERE user_id = %s AND contest_date = CURRENT_DATE
        ''', (user_id,))
        existing = cursor.fetchone()

        if editing:
            if not existing:
                await update.message.reply_text("❌ У вас нет заявки сегодня. Нажмите «Участвовать».")
                context.user_data.pop('contest_edit_photo', None)
                return
            cursor.execute('''
                UPDATE photo_contest
                SET photo_file_id = %s, description = %s, submission_time = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (photo.file_id, caption, existing['id']))
            conn.commit()
            context.user_data.pop('contest_edit_photo', None)
            
            await update.message.reply_text(
                "✅ Фото и описание обновлены!",
            )
            await send_participation_controls(update, context)
            return
        
        if waiting_new:
            if existing:
                await update.message.reply_text("❌ Вы уже участвуете сегодня. Используйте «Редактировать».")
                context.user_data.pop('contest_waiting_photo', None)
                await send_participation_controls(update, context)
                return
            cursor.execute('''
                INSERT INTO photo_contest (user_id, photo_file_id, description)
                VALUES (%s, %s, %s)
            ''', (user_id, photo.file_id, caption))
            conn.commit()
            context.user_data.pop('contest_waiting_photo', None)
            await update.message.reply_text("✅ Вы участвуете в конкурсе!")
            await send_participation_controls(update, context)
            return

        # Если пользователь прислал фото без нажатия кнопок
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Участвовать", callback_data='contest_join')]])
        await update.message.reply_text(
            "ℹ️ Чтобы участвовать в конкурсе, нажмите «Участвовать», затем отправьте фото.",
            reply_markup=kb
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

async def send_participation_controls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить пользователю клавиатуру управления участием."""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отказаться", callback_data='contest_cancel')],
        [InlineKeyboardButton("✏️ Редактировать", callback_data='contest_edit')]
    ])
    try:
        await update.message.reply_text("Управление участием:", reply_markup=kb)
    except Exception:
        pass


async def handle_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка пользовательских callback по конкурсу."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == 'contest_join':
        context.user_data['contest_waiting_photo'] = True
        await query.message.reply_text(
            "📸 Отлично! Отправьте одно фото одним сообщением.\n"
            "Добавьте описание как подпись к фото."
        )
    elif data == 'contest_decline':
        await query.message.reply_text("Хорошо, вы можете присоединиться позже, если передумаете.")
    elif data == 'contest_cancel':
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM photo_contest
                WHERE user_id = %s AND contest_date = CURRENT_DATE
            ''', (user_id,))
            conn.commit()
        context.user_data.pop('contest_waiting_photo', None)
        context.user_data.pop('contest_edit_photo', None)
        await query.message.reply_text("❌ Вы отказались от участия сегодня.")
    elif data == 'contest_edit':
        # Проверим, что есть заявка
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM photo_contest
                WHERE user_id = %s AND contest_date = CURRENT_DATE
            ''', (user_id,))
            row = cursor.fetchone()
        if not row:
            await query.message.reply_text("❌ У вас ещё нет фото сегодня. Нажмите «Участвовать».")
            return
        context.user_data['contest_edit_photo'] = True
        await query.message.reply_text(
            "✏️ Отправьте новое фото одним сообщением с новой подписью — мы заменим текущее фото и описание."
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

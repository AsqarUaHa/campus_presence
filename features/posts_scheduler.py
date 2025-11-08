# ============================================
# FILE: features/posts_scheduler.py
# ============================================

from telegram.ext import ContextTypes
from datetime import datetime
import logging

from config import TIMEZONE
from database.db_manager import get_db

logger = logging.getLogger(__name__)


async def check_scheduled_posts(context: ContextTypes.DEFAULT_TYPE):
    """Проверка и отправка запланированных постов"""
    now = datetime.now(TIMEZONE)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, text, media_id, event_id
            FROM posts
            WHERE status = 'pending'
              AND scheduled_time <= %s
        ''', (now,))
        
        posts = cursor.fetchall()
        
        if not posts:
            return
        
        cursor.execute('''
            SELECT user_id
            FROM users
            WHERE is_registered = TRUE
        ''')
        users = cursor.fetchall()
        
        bot = context.bot
        
        for post in posts:
            success_count = 0
            fail_count = 0
            
            for user in users:
                try:
                    if post['media_id']:
                        await bot.send_photo(
                            chat_id=user['user_id'],
                            photo=post['media_id'],
                            caption=post['text']
                        )
                    else:
                        await bot.send_message(
                            chat_id=user['user_id'],
                            text=post['text']
                        )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Ошибка отправки поста пользователю {user['user_id']}: {e}")
                    fail_count += 1
            
            cursor.execute('''
                UPDATE posts
                SET status = 'sent', sent_at = %s
                WHERE id = %s
            ''', (now, post['id']))
            conn.commit()
            
            logger.info(f"Пост {post['id']} отправлен: успешно {success_count}, ошибок {fail_count}")


async def create_post(user_id: int, text: str, media_id: str, scheduled_time: datetime, event_id: int = None):
    """Создать новый пост"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO posts (created_by, text, media_id, scheduled_time, event_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (user_id, text, media_id, scheduled_time, event_id))
        post_id = cursor.fetchone()['id']
        conn.commit()
    
    return post_id

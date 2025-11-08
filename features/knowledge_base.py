# ============================================
# FILE: features/knowledge_base.py
# ============================================

from telegram import Update
from telegram.ext import ContextTypes
import logging

from database.db_manager import get_db

logger = logging.getLogger(__name__)


async def upload_to_kb(user_id: int, title: str, file_id: str, file_type: str = 'document'):
    """Загрузить файл в базу знаний"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO knowledge_base (title, file_id, file_type, uploaded_by)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (title, file_id, file_type, user_id))
        kb_id = cursor.fetchone()['id']
        conn.commit()
    
    return kb_id


async def handle_kb_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса файла из базы знаний"""
    query = update.callback_query
    
    if not query.data.startswith('kb_file_'):
        return
    
    file_id = int(query.data.replace('kb_file_', ''))
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT file_id, title, file_type
            FROM knowledge_base
            WHERE id = %s
        ''', (file_id,))
        file = cursor.fetchone()
    
    if not file:
        await query.answer("❌ Файл не найден", show_alert=True)
        return
    
    await query.answer("📥 Загрузка файла...")
    
    try:
        await query.message.reply_document(
            document=file['file_id'],
            caption=f"📚 {file['title']}"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки файла из БЗ: {e}")
        await query.message.reply_text("❌ Ошибка при отправке файла.")

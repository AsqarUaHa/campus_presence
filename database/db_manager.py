# ============================================
# FILE: database/db_manager.py
# ============================================

import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging
from config import DATABASE_URL

logger = logging.getLogger(__name__)

@contextmanager
def get_db():
    """Контекстный менеджер для работы с PostgreSQL"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()

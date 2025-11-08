# ============================================
# FILE: database/db_manager.py (ПОЛНАЯ ВЕРСИЯ)
# ============================================

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
import logging
import os

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Пул соединений для оптимизации
connection_pool = None

def init_connection_pool(minconn=1, maxconn=10):
    """Инициализация пула соединений"""
    global connection_pool
    try:
        connection_pool = SimpleConnectionPool(
            minconn,
            maxconn,
            DATABASE_URL
        )
        logger.info(f"✅ Пул соединений создан (min={minconn}, max={maxconn})")
    except Exception as e:
        logger.error(f"❌ Ошибка создания пула соединений: {e}")
        connection_pool = None


@contextmanager
def get_db():
    """
    Контекстный менеджер для работы с PostgreSQL
    Использует пул соединений если доступен, иначе создаёт новое соединение
    """
    conn = None
    from_pool = False
    
    try:
        if connection_pool:
            conn = connection_pool.getconn()
            from_pool = True
        else:
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        
        conn.cursor_factory = RealDictCursor
        yield conn
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Ошибка БД: {e}")
        raise
        
    finally:
        if conn:
            if from_pool and connection_pool:
                connection_pool.putconn(conn)
            else:
                conn.close()


def test_connection():
    """Тестирование подключения к БД"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT version();')
            version = cursor.fetchone()
            logger.info(f"✅ Подключение к PostgreSQL успешно")
            logger.info(f"Версия: {version['version']}")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД: {e}")
        return False


def execute_query(query: str, params: tuple = None, fetch_one=False, fetch_all=False):
    """
    Выполнить SQL-запрос
    
    Args:
        query: SQL запрос
        params: Параметры запроса
        fetch_one: Вернуть одну строку
        fetch_all: Вернуть все строки
    
    Returns:
        Результат запроса или None
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()
            
            conn.commit()
            return True
            
    except Exception as e:
        logger.error(f"Ошибка выполнения запроса: {e}")
        return None


def get_table_stats():
    """Получить статистику по таблицам БД"""
    tables = [
        'users', 'presence', 'geolocation', 'events',
        'posts', 'photo_contest', 'knowledge_base', 'ranks'
    ]
    
    stats = {}
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        for table in tables:
            try:
                cursor.execute(f'SELECT COUNT(*) as count FROM {table}')
                result = cursor.fetchone()
                stats[table] = result['count']
            except Exception as e:
                logger.error(f"Ошибка получения статистики для {table}: {e}")
                stats[table] = -1
    
    return stats


def vacuum_database():
    """Выполнить VACUUM для оптимизации БД"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.set_isolation_level(0)  # Autocommit mode
        cursor = conn.cursor()
        cursor.execute('VACUUM ANALYZE;')
        cursor.close()
        conn.close()
        logger.info("✅ VACUUM выполнен успешно")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка VACUUM: {e}")
        return False


def backup_table(table_name: str) -> list:
    """
    Создать резервную копию таблицы (в памяти)
    
    Returns:
        Список всех строк таблицы
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT * FROM {table_name}')
            data = cursor.fetchall()
            logger.info(f"✅ Резервная копия {table_name}: {len(data)} записей")
            return data
    except Exception as e:
        logger.error(f"❌ Ошибка бэкапа {table_name}: {e}")
        return []


def close_connection_pool():
    """Закрыть пул соединений"""
    global connection_pool
    if connection_pool:
        connection_pool.closeall()
        logger.info("✅ Пул соединений закрыт")
        connection_pool = None

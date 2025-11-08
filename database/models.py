# ============================================
# FILE: database/models.py (ИСПРАВЛЕНО)
# ============================================

from database.db_manager import get_db
import logging

logger = logging.getLogger(__name__)

def init_database():
    """Инициализация всех таблиц БД"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей (расширенная)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                birth_date DATE,
                team_role TEXT,
                phone_number TEXT,
                is_registered BOOLEAN DEFAULT FALSE,
                is_admin BOOLEAN DEFAULT FALSE,
                total_checkins INTEGER DEFAULT 0,
                current_rank TEXT DEFAULT 'Новичок',
                geo_consent BOOLEAN DEFAULT FALSE,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица мероприятий (новая)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                description TEXT,
                created_by BIGINT REFERENCES users(user_id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица присутствия (с event_id)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS presence (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                event_id INTEGER REFERENCES events(id),
                check_in_time TIMESTAMP,
                check_out_time TIMESTAMP,
                date DATE,
                status TEXT,
                latitude REAL,
                longitude REAL
            )
        ''')
        
        # Таблица геолокации
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS geolocation (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                latitude REAL,
                longitude REAL,
                distance_to_campus REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_near_campus BOOLEAN
            )
        ''')
        
        # Таблица постов (новая)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES events(id),
                text TEXT NOT NULL,
                media_id TEXT,
                scheduled_time TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'pending',
                created_by BIGINT REFERENCES users(user_id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP
            )
        ''')
        
        # Таблица конкурса фото (новая)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photo_contest (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                photo_file_id TEXT NOT NULL,
                event_id INTEGER REFERENCES events(id),
                votes INTEGER DEFAULT 0,
                submission_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_winner BOOLEAN DEFAULT FALSE,
                contest_date DATE DEFAULT CURRENT_DATE
            )
        ''')
        
        # Таблица голосов за фото (новая)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS photo_votes (
                id SERIAL PRIMARY KEY,
                photo_id INTEGER REFERENCES photo_contest(id),
                voter_id BIGINT REFERENCES users(user_id),
                vote_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(photo_id, voter_id)
            )
        ''')
        
        # Таблица базы знаний (новая)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_type TEXT,
                uploaded_by BIGINT REFERENCES users(user_id),
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица рангов (новая)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ranks (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                min_checkins INTEGER NOT NULL,
                emoji TEXT DEFAULT '⭐'
            )
        ''')
        
        # Заполняем ранги, если таблица пустая
        cursor.execute('SELECT COUNT(*) AS count FROM ranks')
        if cursor.fetchone()['count'] == 0:
            ranks_data = [
                ('Новичок', 0, '🌱'),
                ('Идеолог', 5, '💡'),
                ('Реформатор', 15, '🔥'),
                ('Философ', 30, '🧠')
            ]
            cursor.executemany(
                'INSERT INTO ranks (name, min_checkins, emoji) VALUES (%s, %s, %s)',
                ranks_data
            )
        
        conn.commit()
        logger.info("База данных инициализирована успешно")


def is_user_registered(user_id: int) -> bool:
    """Проверка, зарегистрирован ли пользователь"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT is_registered FROM users WHERE user_id = %s',
            (user_id,)
        )
        result = cursor.fetchone()
        return result['is_registered'] if result else False


def is_user_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT is_admin FROM users WHERE user_id = %s',
            (user_id,)
        )
        result = cursor.fetchone()
        return result['is_admin'] if result else False


def get_user_profile(user_id: int) -> dict:
    """Получить профиль пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, first_name, last_name, birth_date,
                   team_role, phone_number, is_registered, total_checkins,
                   current_rank, geo_consent
            FROM users
            WHERE user_id = %s
        ''', (user_id,))
        return cursor.fetchone()


def create_user(user_id: int, username: str, full_name: str):
    """Создать запись пользователя при первом старте"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        ''', (user_id, username, full_name))
        conn.commit()


def complete_registration(user_id: int, data: dict):
    """Завершить регистрацию пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET first_name = %s,
                last_name = %s,
                birth_date = %s,
                team_role = %s,
                phone_number = %s,
                is_registered = TRUE,
                geo_consent = TRUE,
                last_update = CURRENT_TIMESTAMP
            WHERE user_id = %s
        ''', (
            data['first_name'],
            data['last_name'],
            data['birth_date'],
            data['team_role'],
            data['phone_number'],
            user_id
        ))
        conn.commit()


def increment_checkins(user_id: int):
    """Увеличить счётчик чекинов и обновить ранг"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Увеличиваем счётчик
        cursor.execute('''
            UPDATE users
            SET total_checkins = total_checkins + 1
            WHERE user_id = %s
            RETURNING total_checkins
        ''', (user_id,))
        
        total = cursor.fetchone()['total_checkins']
        
        # Определяем новый ранг
        cursor.execute('''
            SELECT name FROM ranks
            WHERE min_checkins <= %s
            ORDER BY min_checkins DESC
            LIMIT 1
        ''', (total,))
        
        new_rank = cursor.fetchone()['name']
        
        # Получаем текущий ранг
        cursor.execute(
            'SELECT current_rank FROM users WHERE user_id = %s',
            (user_id,)
        )
        old_rank = cursor.fetchone()['current_rank']
        
        # Обновляем ранг, если изменился
        if new_rank != old_rank:
            cursor.execute('''
                UPDATE users
                SET current_rank = %s
                WHERE user_id = %s
            ''', (new_rank, user_id))
            conn.commit()
            return new_rank  # Возвращаем новый ранг для уведомления
        
        conn.commit()
        return None


def get_all_users_status():
    """Получить всех пользователей с индикатором присутствия"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                u.user_id,
                u.first_name,
                u.last_name,
                u.username,
                u.team_role,
                u.current_rank,
                p.status as presence_status,
                g.is_near_campus,
                g.timestamp as last_geo_update
            FROM users u
            LEFT JOIN (
                SELECT DISTINCT ON (user_id) user_id, status
                FROM presence
                WHERE date = CURRENT_DATE
                ORDER BY user_id, check_in_time DESC
            ) p ON u.user_id = p.user_id
            LEFT JOIN (
                SELECT DISTINCT ON (user_id) user_id, is_near_campus, timestamp
                FROM geolocation
                ORDER BY user_id, timestamp DESC
            ) g ON u.user_id = g.user_id
            WHERE u.is_registered = TRUE
            ORDER BY u.first_name, u.last_name
        ''')
        return cursor.fetchall()


def get_active_event():
    """Получить активное мероприятие"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM events
            WHERE start_time <= CURRENT_TIMESTAMP
              AND end_time >= CURRENT_TIMESTAMP
            ORDER BY start_time DESC
            LIMIT 1
        ''')
        return cursor.fetchone()

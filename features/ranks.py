# ============================================
# FILE: features/ranks.py (ПОЛНАЯ ВЕРСИЯ)
# ============================================

from database.db_manager import get_db
import logging

logger = logging.getLogger(__name__)


def get_rank_by_checkins(checkins: int) -> dict:
    """Получить ранг по количеству чекинов"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, emoji, min_checkins
            FROM ranks
            WHERE min_checkins <= %s
            ORDER BY min_checkins DESC
            LIMIT 1
        ''', (checkins,))
        
        result = cursor.fetchone()
        if result:
            return {
                'name': result['name'],
                'emoji': result['emoji'],
                'min_checkins': result['min_checkins']
            }
        
        # Если не найдено, вернуть Новичок
        return {'name': 'Новичок', 'emoji': '🌱', 'min_checkins': 0}


def get_next_rank(current_checkins: int) -> dict:
    """Получить следующий ранг"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, emoji, min_checkins
            FROM ranks
            WHERE min_checkins > %s
            ORDER BY min_checkins ASC
            LIMIT 1
        ''', (current_checkins,))
        
        result = cursor.fetchone()
        if result:
            return {
                'name': result['name'],
                'emoji': result['emoji'],
                'min_checkins': result['min_checkins'],
                'remaining': result['min_checkins'] - current_checkins
            }
        
        return None


def get_all_ranks() -> list:
    """Получить все ранги"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, emoji, min_checkins
            FROM ranks
            ORDER BY min_checkins ASC
        ''')
        return cursor.fetchall()


def get_user_rank_info(user_id: int) -> dict:
    """Получить полную информацию о ранге пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем данные пользователя
        cursor.execute('''
            SELECT total_checkins, current_rank
            FROM users
            WHERE user_id = %s
        ''', (user_id,))
        
        user = cursor.fetchone()
        if not user:
            return None
        
        # Получаем информацию о текущем ранге
        cursor.execute('''
            SELECT emoji, min_checkins
            FROM ranks
            WHERE name = %s
        ''', (user['current_rank'],))
        
        current_rank = cursor.fetchone()
        
        # Получаем следующий ранг
        next_rank = get_next_rank(user['total_checkins'])
        
        return {
            'current_rank': user['current_rank'],
            'emoji': current_rank['emoji'] if current_rank else '🌱',
            'total_checkins': user['total_checkins'],
            'next_rank': next_rank
        }


def get_leaderboard(limit: int = 10) -> list:
    """Получить топ пользователей по рангам"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                u.user_id,
                u.first_name,
                u.last_name,
                u.username,
                u.team_role,
                u.total_checkins,
                u.current_rank,
                r.emoji
            FROM users u
            JOIN ranks r ON u.current_rank = r.name
            WHERE u.is_registered = TRUE
            ORDER BY u.total_checkins DESC, u.registration_date ASC
            LIMIT %s
        ''', (limit,))
        
        return cursor.fetchall()


def update_user_rank(user_id: int, new_rank: str) -> bool:
    """Обновить ранг пользователя вручную"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users
                SET current_rank = %s, last_update = CURRENT_TIMESTAMP
                WHERE user_id = %s
            ''', (new_rank, user_id))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления ранга: {e}")
        return False


def check_and_update_rank(user_id: int) -> str:
    """
    Проверить и обновить ранг пользователя на основе чекинов
    Возвращает новый ранг, если произошло повышение, иначе None
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем текущие данные
        cursor.execute('''
            SELECT total_checkins, current_rank
            FROM users
            WHERE user_id = %s
        ''', (user_id,))
        
        user = cursor.fetchone()
        if not user:
            return None
        
        # Определяем правильный ранг по чекинам
        correct_rank = get_rank_by_checkins(user['total_checkins'])
        
        # Если ранг изменился
        if correct_rank['name'] != user['current_rank']:
            cursor.execute('''
                UPDATE users
                SET current_rank = %s
                WHERE user_id = %s
            ''', (correct_rank['name'], user_id))
            conn.commit()
            
            logger.info(f"Пользователь {user_id} повышен до ранга {correct_rank['name']}")
            return correct_rank['name']
        
        return None


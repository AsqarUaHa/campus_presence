
# ============================================
# FILE: utils/geo_utils.py
# ============================================

from geopy.distance import geodesic
from datetime import datetime, timedelta
from config import TIMEZONE, NEAR_CAMPUS_RADIUS


def calculate_distance(lat1, lon1, lat2, lon2):
    """Рассчитать расстояние между двумя точками в метрах"""
    coords1 = (lat1, lon1)
    coords2 = (lat2, lon2)
    return geodesic(coords1, coords2).meters


def get_status_indicator(presence_status, is_near_campus, last_geo_update):
    """
    Определить индикатор статуса пользователя
    
    Возвращает кортеж: (emoji, text_status)
    """
    # 🟢 В кампусе
    if presence_status == 'in_campus':
        return ('🟢', 'В кампусе')
    
    # 🟡 Рядом с кампусом
    if is_near_campus and last_geo_update:
        # Проверяем, что геолокация не старше 30 минут
        if isinstance(last_geo_update, str):
            last_geo_update = datetime.fromisoformat(last_geo_update)
        
        if last_geo_update.tzinfo is None:
            last_geo_update = last_geo_update.replace(tzinfo=TIMEZONE)
        
        time_diff = datetime.now(TIMEZONE) - last_geo_update
        if time_diff < timedelta(minutes=30):
            return ('🟡', 'Рядом')
    
    # 🔴 Вне кампуса
    return ('🔴', 'Вне кампуса')


def format_distance(distance_meters):
    """Форматировать расстояние для отображения"""
    if distance_meters < 1000:
        return f"{int(distance_meters)}м"
    else:
        return f"{distance_meters / 1000:.1f}км"

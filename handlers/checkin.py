# ============================================
# FILE: handlers/checkin.py
# ============================================

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime, timezone
from geopy.distance import geodesic
import logging

from config import CAMPUS_LATITUDE, CAMPUS_LONGITUDE, PROXIMITY_RADIUS, TIMEZONE
from database.db_manager import get_db
from database.models import increment_checkins, get_active_event
from utils.keyboards import get_main_keyboard
from utils.decorators import registered_only

logger = logging.getLogger(__name__)


def get_local_time():
    """Получить текущее локальное время"""
    return datetime.now(TIMEZONE)


@registered_only
async def request_checkin_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос геолокации для check-in"""
    user_id = update.effective_user.id
    
    # Проверяем geo_consent
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT geo_consent FROM users WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        
        if not result or not result['geo_consent']:
            await update.message.reply_text(
                "❌ Для отметки в кампусе необходимо разрешение на использование геолокации.\n\n"
                "Перейдите в ⚙️ Настройки и включите геолокацию.",
                reply_markup=get_main_keyboard()
            )
            return
    
    # Проверяем, не отмечен ли уже сегодня
    today = get_local_time().date()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM presence
            WHERE user_id = %s AND date = %s AND status = 'in_campus'
        ''', (user_id, today))
        
        if cursor.fetchone():
            await update.message.reply_text(
                "✅ Вы уже отмечены в кампусе сегодня!",
                reply_markup=get_main_keyboard()
            )
            return
    
    # Создаём кнопку для отправки геолокации
    keyboard = [
        [KeyboardButton("📍 Отправить мою геолокацию", request_location=True)],
        [KeyboardButton("❌ Отмена")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "📍 Для отметки в кампусе отправьте вашу текущую геолокацию.\n\n"
        "⚠️ Вы должны находиться в пределах 300 метров от кампуса.",
        reply_markup=reply_markup
    )
    
    # Сохраняем флаг, что пользователь запросил check-in
    context.user_data['awaiting_checkin_location'] = True


async def handle_checkin_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка геолокации для check-in"""
    user_id = update.effective_user.id
    location = update.message.location
    
    # Проверяем, ожидали ли мы геолокацию для check-in
    if not context.user_data.get('awaiting_checkin_location'):
        # Это обычная геолокация, обрабатываем как обновление позиции
        await handle_location_update(update, context)
        return
    
    # Очищаем флаг
    context.user_data['awaiting_checkin_location'] = False
    
    # Рассчитываем расстояние до кампуса
    user_coords = (location.latitude, location.longitude)
    campus_coords = (CAMPUS_LATITUDE, CAMPUS_LONGITUDE)
    distance = geodesic(user_coords, campus_coords).meters
    
    # Проверяем расстояние (должно быть <= 300м)
    if distance > PROXIMITY_RADIUS:
        await update.message.reply_text(
            f"❌ Вы находитесь слишком далеко от кампуса!\n\n"
            f"📏 Расстояние: {int(distance)} метров\n"
            f"⚠️ Необходимо: не более {PROXIMITY_RADIUS} метров\n\n"
            "Подойдите ближе к кампусу и попробуйте снова.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Успешный check-in
    now = get_local_time()
    today = now.date()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем активное мероприятие (если есть)
        active_event = get_active_event()
        event_id = active_event['id'] if active_event else None
        
        # Создаём запись о присутствии
        cursor.execute('''
            INSERT INTO presence (
                user_id, event_id, check_in_time, date, status,
                latitude, longitude
            )
            VALUES (%s, %s, %s, %s, 'in_campus', %s, %s)
        ''', (user_id, event_id, now, today, location.latitude, location.longitude))
        
        # Сохраняем геолокацию
        is_near = distance <= 1000  # NEAR_CAMPUS_RADIUS
        cursor.execute('''
            INSERT INTO geolocation (
                user_id, latitude, longitude, distance_to_campus, is_near_campus
            )
            VALUES (%s, %s, %s, %s, %s)
        ''', (user_id, location.latitude, location.longitude, distance, is_near))
        
        conn.commit()
    
    # Увеличиваем счётчик и проверяем ранг
    new_rank = increment_checkins(user_id)
    
    # Формируем сообщение
    message = f"""
✅ Вы успешно отметились в кампусе!

📍 Расстояние до центра: {int(distance)}м
🕐 Время: {now.strftime('%H:%M')}
    """
    
    if active_event:
        message += f"\n🎯 Мероприятие: {active_event['name']}"
    
    # Если повысился ранг
    if new_rank:
        # Получаем emoji ранга
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT emoji FROM ranks WHERE name = %s', (new_rank,))
            emoji = cursor.fetchone()['emoji']
        
        message += f"\n\n🎉 **Поздравляем!**\n{emoji} Вы получили новый ранг: **{new_rank}**!"
    
    await update.message.reply_text(message, reply_markup=get_main_keyboard())


@registered_only
async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отметка ухода из кампуса"""
    user_id = update.effective_user.id
    now = get_local_time()
    today = now.date()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Находим активную отметку
        cursor.execute('''
            SELECT id, check_in_time FROM presence
            WHERE user_id = %s AND date = %s AND status = 'in_campus'
            ORDER BY check_in_time DESC LIMIT 1
        ''', (user_id, today))
        
        record = cursor.fetchone()
        
        if not record:
            await update.message.reply_text(
                "❌ Вы не отмечены в кампусе!",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Обновляем запись
        cursor.execute('''
            UPDATE presence
            SET check_out_time = %s, status = 'left'
            WHERE id = %s
        ''', (now, record['id']))
        conn.commit()
        
        # Рассчитываем время пребывания
        check_in = record['check_in_time']
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=timezone.utc)
        duration = now - check_in.astimezone(TIMEZONE)
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)
    
    await update.message.reply_text(
        f"👋 Вы отметились как ушедший!\n\n"
        f"🕐 Время ухода: {now.strftime('%H:%M')}\n"
        f"⏱ Время пребывания: {hours}ч {minutes}мин",
        reply_markup=get_main_keyboard()
    )


async def handle_location_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновление геолокации пользователя (не check-in)"""
    user_id = update.effective_user.id
    location = update.message.location
    
    # Проверяем geo_consent
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT geo_consent FROM users WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        
        if not result or not result['geo_consent']:
            return
    
    # Рассчитываем расстояние
    user_coords = (location.latitude, location.longitude)
    campus_coords = (CAMPUS_LATITUDE, CAMPUS_LONGITUDE)
    distance = geodesic(user_coords, campus_coords).meters
    is_near = distance <= 1000  # NEAR_CAMPUS_RADIUS
    
    # Сохраняем геолокацию
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO geolocation (
                user_id, latitude, longitude, distance_to_campus, is_near_campus
            )
            VALUES (%s, %s, %s, %s, %s)
        ''', (user_id, location.latitude, location.longitude, distance, is_near))
        conn.commit()
    
    status_text = f"🟡 Вы рядом с кампусом ({int(distance)}м)" if is_near else f"📍 Расстояние до кампуса: {int(distance)}м"
    
    await update.message.reply_text(
        f"✅ Геолокация обновлена!\n{status_text}",
        reply_markup=get_main_keyboard()
    )

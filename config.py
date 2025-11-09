# ============================================
# FILE: config.py
# ============================================

import os
from datetime import timezone, timedelta

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Координаты кампуса
CAMPUS_LATITUDE = float(os.getenv("CAMPUS_LATITUDE", "43.2220"))
CAMPUS_LONGITUDE = float(os.getenv("CAMPUS_LONGITUDE", "76.8512"))

# Радиусы проверки (в метрах)
PROXIMITY_RADIUS = 300      # Для check-in
NEAR_CAMPUS_RADIUS = 1000   # Для статуса "Рядом"

# Часовой пояс
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "5"))
TIMEZONE = timezone(timedelta(hours=TIMEZONE_OFFSET))

# Администраторы (через переменную окружения, разделённые запятой)
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# Ранги и их пороги
RANKS = {
    "Новичок": 0,
    "Идеолог": 5,
    "Реформатор": 15,
    "Философ": 30
}

# Время завершения конкурсов
CONTEST_END_TIME = "02:00"

# Состояния для диалогов (FSM)
class States:
    # Регистрация
    REGISTRATION_FIRST_NAME = 1
    REGISTRATION_LAST_NAME = 2
    REGISTRATION_BIRTH_DATE = 3
    REGISTRATION_TEAM_ROLE = 4
    REGISTRATION_PHONE = 5
    
    # Админка - создание поста
    ADMIN_POST_TEXT = 10
    ADMIN_POST_MEDIA = 11
    ADMIN_POST_DATETIME = 12
    # Админка - управление постами
    ADMIN_POST_MANAGE = 13
    ADMIN_POST_EDIT_TEXT = 14
    ADMIN_POST_EDIT_TIME = 15
    
    # Админка - создание мероприятия
    ADMIN_EVENT_NAME = 20
    ADMIN_EVENT_START = 21
    ADMIN_EVENT_END = 22
    ADMIN_EVENT_DESC = 23
    # Админка - управление мероприятиями
    ADMIN_EVENT_MANAGE = 24
    ADMIN_EVENT_EDIT_NAME = 25
    ADMIN_EVENT_EDIT_START = 26
    ADMIN_EVENT_EDIT_END = 27
    ADMIN_EVENT_EDIT_DESC = 28
    
    # База знаний - загрузка
    ADMIN_KB_TITLE = 30
    ADMIN_KB_FILE = 31
    # База знаний - управление
    ADMIN_KB_MANAGE = 32
    ADMIN_KB_RENAME = 33
    
    # Конкурс фото
    CONTEST_PHOTO_UPLOAD = 40
    
    # Редактирование профиля
    EDIT_PROFILE_FIELD = 50

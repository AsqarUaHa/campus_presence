import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CAMPUS_LATITUDE = float(os.getenv("CAMPUS_LATITUDE", 43.239581))
CAMPUS_LONGITUDE = float(os.getenv("CAMPUS_LONGITUDE", 76.962465))
PROXIMITY_RADIUS = int(os.getenv("PROXIMITY_RADIUS", 500))
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", 5))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

from enum import Enum, auto

class States(Enum):
    REGISTRATION_FIRST_NAME = auto()
    REGISTRATION_LAST_NAME = auto()
    REGISTRATION_BIRTH_DATE = auto()
    REGISTRATION_TEAM_ROLE = auto()
    REGISTRATION_PHONE = auto()

    ADMIN_POST_TEXT = auto()
    ADMIN_POST_MEDIA = auto()
    ADMIN_POST_DATETIME = auto()

    ADMIN_EVENT_NAME = auto()
    ADMIN_EVENT_START = auto()
    ADMIN_EVENT_END = auto()
    ADMIN_EVENT_DESC = auto()

    ADMIN_KB_TITLE = auto()
    ADMIN_KB_FILE = auto()


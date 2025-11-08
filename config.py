import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CAMPUS_LATITUDE = float(os.getenv("CAMPUS_LATITUDE", 43.239581))
CAMPUS_LONGITUDE = float(os.getenv("CAMPUS_LONGITUDE", 76.962465))
PROXIMITY_RADIUS = int(os.getenv("PROXIMITY_RADIUS", 500))
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", 5))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]


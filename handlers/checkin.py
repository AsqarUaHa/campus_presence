from telegram import Update
from telegram.ext import ContextTypes
from geopy.distance import distance
from config import CAMPUS_LATITUDE, CAMPUS_LONGITUDE, PROXIMITY_RADIUS

async def handle_checkin_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_loc = (update.message.location.latitude, update.message.location.longitude)
    campus_loc = (CAMPUS_LATITUDE, CAMPUS_LONGITUDE)
    dist = distance(user_loc, campus_loc).meters

    if dist <= PROXIMITY_RADIUS:
        await update.message.reply_text("📍 Вы отметились в кампусе! Добро пожаловать 👋")
    else:
        await update.message.reply_text("⚠️ Вы находитесь слишком далеко от кампуса.")


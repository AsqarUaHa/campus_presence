from telegram import ReplyKeyboardMarkup

def main_menu():
    return ReplyKeyboardMarkup([
        ["📍 Check-in", "📘 База знаний"],
        ["🎯 Конкурсы", "⚙️ Профиль"]
    ], resize_keyboard=True)


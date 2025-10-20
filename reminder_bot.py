import telebot
import re
import time
import threading
from datetime import datetime
import dateparser
from supabase import create_client, Client
import os

# === Environment Variables ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# === Initialize Telegram and Supabase ===
bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def add_reminder(chat_id, task, remind_time):
    supabase.table("reminders").insert({
        "chat_id": chat_id,
        "task": task,
        "remind_time": remind_time.isoformat(),
        "created_at": datetime.utcnow().isoformat()
    }).execute()
    print(f"💾 Saved reminder: {task} at {remind_time}")


def get_due_reminders():
    now = datetime.utcnow().isoformat()
    data = supabase.table("reminders").select("*").lte("remind_time", now).execute()
    return data.data if data.data else []


def delete_reminder(rid):
    supabase.table("reminders").delete().eq("id", rid).execute()
    print(f"🗑️ Deleted reminder ID {rid}")


def check_reminders():
    while True:
        due = get_due_reminders()
        for r in due:
            try:
                bot.send_message(r["chat_id"], f"🔔 Reminder: {r['task']}")
                delete_reminder(r["id"])
            except Exception as e:
                print(f"Error sending reminder: {e}")
        time.sleep(30)


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(message, (
        "👋 Hey there! I’m your reminder bot.\n\n"
        "You can tell me things like:\n"
        "🕐 `remind me to drink water at 8 pm`\n"
        "⏰ `remind me to call mom in 10 minutes`\n\n"
        "I'll remember and notify you at the right time!"
    ))


@bot.message_handler(func=lambda msg: True)
def handle_message(message):
    text = message.text.lower().strip()
    match = re.search(r"remind me to (.+) (?:at|in) (.+)", text)
    if match:
        task = match.group(1).strip()
        time_text = match.group(2).strip()
        remind_time = dateparser.parse(time_text, settings={'PREFER_DATES_FROM': 'future'})
        if not remind_time:
            bot.reply_to(message, "😅 I couldn't understand the time. Try: 'in 10 minutes' or 'at 8 pm'")
            return
        add_reminder(message.chat.id, task, remind_time)
        bot.reply_to(message, f"✅ Got it! I'll remind you to *{task}* at {remind_time.strftime('%I:%M %p, %b %d')}", parse_mode="Markdown")
    else:
        bot.reply_to(message, "Try saying: 'remind me to drink water at 8 pm' or 'remind me to call mom in 10 minutes'")


# === Background Thread ===
threading.Thread(target=check_reminders, daemon=True).start()

print("🤖 Bot running on Railway with Supabase storage...")
bot.infinity_polling()
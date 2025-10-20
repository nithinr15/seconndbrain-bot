import telebot
import re
import time
import threading
from datetime import datetime
import dateparser
import json
import os

# 🔑 Replace this with your real bot token from BotFather
import os
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# 📁 File to store reminders
REMINDER_FILE = "reminders.json"

# Load existing reminders from file
def load_reminders():
    if os.path.exists(REMINDER_FILE):
        with open(REMINDER_FILE, "r") as f:
            try:
                data = json.load(f)
                # Convert time strings back to datetime objects
                for r in data:
                    r["time"] = datetime.fromisoformat(r["time"])
                print(f"✅ Loaded {len(data)} reminders from file.")
                return data
            except json.JSONDecodeError:
                return []
    return []

# Save reminders to file
def save_reminders():
    data = []
    for r in reminders:
        data.append({
            "id": r["id"],
            "chat_id": r["chat_id"],
            "task": r["task"],
            "time": r["time"].isoformat()
        })
    with open(REMINDER_FILE, "w") as f:
        json.dump(data, f, indent=2)

# Initialize reminder list
reminders = load_reminders()

def next_id():
    if not reminders:
        return 1
    return max(r["id"] for r in reminders) + 1

def add_reminder(chat_id, task, remind_time):
    rid = next_id()
    reminders.append({
        'id': rid,
        'chat_id': chat_id,
        'task': task,
        'time': remind_time
    })
    save_reminders()
    print(f"💾 Reminder added (id={rid}): {task} at {remind_time}")
    return rid

def delete_reminder_by_id(rid):
    for r in reminders:
        if r["id"] == rid:
            reminders.remove(r)
            save_reminders()
            return True
    return False

def check_reminders():
    """Background thread to send reminders at correct time"""
    while True:
        now = datetime.now()
        for reminder in reminders[:]:
            if now >= reminder['time']:
                try:
                    bot.send_message(reminder['chat_id'], f"🔔 Reminder: {reminder['task']}")
                except Exception as e:
                    print("Error sending reminder:", e)
                reminders.remove(reminder)
                save_reminders()
        time.sleep(30)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, (
        "👋 Hey there! I’m your personal reminder bot.\n\n"
        "You can tell me things like:\n"
        "🕐 `remind me to drink water at 8 pm`\n"
        "⏰ `remind me to call mom in 10 minutes`\n\n"
        "Commands:\n"
        "/list - show upcoming reminders\n"
        "/delete <id> - delete a reminder by id\n\n"
        "I’ll remember and notify you at the right time!"
    ))

@bot.message_handler(commands=['list'])
def handle_list(message):
    user_id = message.chat.id
    user_reminders = [r for r in reminders if r["chat_id"] == user_id]
    if not user_reminders:
        bot.reply_to(message, "You have no upcoming reminders.")
        return

    lines = []
    for r in sorted(user_reminders, key=lambda x: x["time"]):
        lines.append(f"ID {r['id']}: {r['task']} — at {r['time'].strftime('%I:%M %p, %b %d')}")
    reply = "🗒️ Your upcoming reminders:\n\n" + "\n".join(lines)
    bot.reply_to(message, reply)

@bot.message_handler(commands=['delete'])
def handle_delete(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /delete <id>  (get the id from /list)")
        return
    try:
        rid = int(parts[1])
    except ValueError:
        bot.reply_to(message, "ID must be a number. Example: /delete 3")
        return

    if delete_reminder_by_id(rid):
        bot.reply_to(message, f"✅ Deleted reminder ID {rid}.")
    else:
        bot.reply_to(message, f"Could not find reminder with ID {rid}.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.lower().strip()

    # Match patterns like "remind me to drink water at 8 pm" or "remind me to call mom in 10 minutes"
    match = re.search(r"remind me to (.+) (?:at|in) (.+)", text)
    
    if match:
        task = match.group(1).strip()
        time_text = match.group(2).strip()

        remind_time = dateparser.parse(time_text, settings={'PREFER_DATES_FROM': 'future'})
        if not remind_time:
            bot.reply_to(message, "Hmm 🤔 I couldn’t understand the time. Try something like 'in 10 minutes' or 'at 8 pm'.")
            return

        rid = add_reminder(message.chat.id, task, remind_time)
        bot.reply_to(message, f"✅ Got it! (ID {rid}) I'll remind you to *{task}* at {remind_time.strftime('%I:%M %p, %b %d')} 👍", parse_mode="Markdown")
    else:
        bot.reply_to(message, "Try saying:\n'remind me to drink water at 8 pm' or 'remind me to call mom in 10 minutes'")

# 🧵 Background thread to check reminders
threading.Thread(target=check_reminders, daemon=True).start()

print("🤖 Bot running with persistent memory and /list support...")
bot.infinity_polling()
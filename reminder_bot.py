import telebot
import re
import time
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # built-in for Python 3.9+
import dateparser
from supabase import create_client, Client
import os

# === Environment Variables ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# === Timezone Setup ===
IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")

# === Initialize Telegram and Supabase ===
bot = telebot.TeleBot(BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# --- Supabase Helper Functions ---
def add_reminder(chat_id, task, remind_time, recurring=False, frequency=None):
    # Store in UTC for consistency
    utc_time = remind_time.astimezone(UTC)
    supabase.table("reminders").insert({
        "chat_id": chat_id,
        "task": task,
        "remind_time": utc_time.isoformat(),
        "recurring": recurring,
        "frequency": frequency,
        "created_at": datetime.now(UTC).isoformat()
    }).execute()
    print(f"💾 Saved reminder: {task} at {remind_time} IST | {utc_time} UTC")


def get_due_reminders():
    now = datetime.now(UTC).isoformat()
    data = supabase.table("reminders").select("*").lte("remind_time", now).execute()
    return data.data if data.data else []


def delete_reminder(rid):
    supabase.table("reminders").delete().eq("id", rid).execute()
    print(f"🗑️ Deleted reminder ID {rid}")


def update_reminder_time(rid, new_time):
    utc_time = new_time.astimezone(UTC)
    supabase.table("reminders").update({"remind_time": utc_time.isoformat()}).eq("id", rid).execute()
    print(f"🔁 Rescheduled recurring reminder ID {rid} to {new_time} IST")


def get_user_reminders(chat_id):
    data = supabase.table("reminders").select("*").eq("chat_id", chat_id).order("remind_time", desc=False).execute()
    return data.data if data.data else []


def get_user_reminders_filtered(chat_id, start, end):
    data = (
        supabase.table("reminders")
        .select("*")
        .eq("chat_id", chat_id)
        .gte("remind_time", start.astimezone(UTC).isoformat())
        .lte("remind_time", end.astimezone(UTC).isoformat())
        .order("remind_time", desc=False)
        .execute()
    )
    return data.data if data.data else []


def check_reminders():
    """Background thread that checks due reminders every 30 seconds"""
    while True:
        due = get_due_reminders()
        for r in due:
            try:
                bot.send_message(r["chat_id"], f"🔔 Reminder: {r['task']}")
                # Handle recurring reminders
                if r.get("recurring"):
                    freq = r.get("frequency", "daily")
                    remind_time = datetime.fromisoformat(r["remind_time"]).astimezone(IST)
                    if freq == "daily":
                        next_time = remind_time + timedelta(days=1)
                    elif freq == "weekly":
                        next_time = remind_time + timedelta(weeks=1)
                    else:
                        next_time = remind_time + timedelta(days=1)
                    update_reminder_time(r["id"], next_time)
                else:
                    delete_reminder(r["id"])
            except Exception as e:
                print(f"Error sending reminder: {e}")
        time.sleep(30)


# --- Telegram Command Handlers ---
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(message, (
        "👋 Hey there! I’m your personal reminder bot.\n\n"
        "You can tell me things like:\n"
        "🕐 `remind me to drink water at 8 pm`\n"
        "🔁 `remind me every day at 8am to meditate`\n\n"
        "Commands:\n"
        "/list - show all upcoming reminders\n"
        "/list today - show today's reminders\n"
        "/list week - show this week's reminders\n"
        "/delete <id> - delete a reminder by its ID\n\n"
        "🕓 Timezone: *IST (India Standard Time)*\n"
        "I'll remember and notify you at the right time!"
    ), parse_mode="Markdown")


@bot.message_handler(commands=["list"])
def handle_list(message):
    """Shows upcoming reminders for this user, or filtered ones"""
    chat_id = message.chat.id
    args = message.text.split()

    now = datetime.now(IST)
    if len(args) > 1 and args[1].lower() == "today":
        start = datetime(now.year, now.month, now.day, tzinfo=IST)
        end = start + timedelta(days=1)
        reminders = get_user_reminders_filtered(chat_id, start, end)
    elif len(args) > 1 and args[1].lower() == "week":
        start = datetime(now.year, now.month, now.day, tzinfo=IST)
        end = start + timedelta(days=7)
        reminders = get_user_reminders_filtered(chat_id, start, end)
    else:
        reminders = get_user_reminders(chat_id)

    if not reminders:
        bot.reply_to(message, "📭 You have no upcoming reminders.")
        return

    lines = ["🗒️ *Your Upcoming Reminders:*"]
    for r in reminders:
        rid = r["id"]
        task = r["task"]
        t = datetime.fromisoformat(r["remind_time"]).astimezone(IST).strftime("%I:%M %p, %b %d")
        rec = " (🔁 daily)" if r.get("recurring") else ""
        lines.append(f"• ID {rid}: {task}{rec} — ⏰ {t} IST")

    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")


@bot.message_handler(commands=["delete"])
def handle_delete(message):
    """Deletes a reminder by its ID"""
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: `/delete <id>`\nExample: `/delete 3`", parse_mode="Markdown")
        return

    try:
        rid = int(parts[1])
        delete_reminder(rid)
        bot.reply_to(message, f"✅ Deleted reminder ID {rid}.")
    except ValueError:
        bot.reply_to(message, "⚠️ Please provide a valid numeric ID. Example: `/delete 3`", parse_mode="Markdown")


@bot.message_handler(func=lambda msg: True)
def handle_message(message):
    """Handles natural language reminder creation"""
    text = message.text.lower().strip()

    # --- Recurring Reminder Pattern ---
    recurring_match = re.search(r"remind me every (day|week|daily|weekly) at (.+) to (.+)", text)
    if recurring_match:
        frequency = "daily" if "day" in recurring_match.group(1) else "weekly"
        time_text = recurring_match.group(2).strip()
        task = recurring_match.group(3).strip()

        remind_time = dateparser.parse(
            time_text,
            settings={
                'PREFER_DATES_FROM': 'future',
                'TIMEZONE': 'Asia/Kolkata',
                'RETURN_AS_TIMEZONE_AWARE': True
            }
        )
        if not remind_time:
            bot.reply_to(message, "😅 I couldn't understand the time. Try: 'every day at 8am' or 'every week at 6pm'")
            return

        remind_time = remind_time.astimezone(IST)
        add_reminder(message.chat.id, task, remind_time, recurring=True, frequency=frequency)
        bot.reply_to(message, f"✅ Got it! I'll remind you *{frequency}* to *{task}* at {remind_time.strftime('%I:%M %p')} IST ⏰", parse_mode="Markdown")
        return

    # --- One-time Reminder Pattern ---
    match = re.search(r"remind me to (.+) (?:at|in) (.+)", text)
    if match:
        task = match.group(1).strip()
        time_text = match.group(2).strip()

        remind_time = dateparser.parse(
            time_text,
            settings={
                'PREFER_DATES_FROM': 'future',
                'TIMEZONE': 'Asia/Kolkata',
                'RETURN_AS_TIMEZONE_AWARE': True
            }
        )
        if not remind_time:
            bot.reply_to(message, "😅 I couldn't understand the time. Try: 'in 10 minutes' or 'at 8 pm'")
            return

        remind_time = remind_time.astimezone(IST)
        add_reminder(message.chat.id, task, remind_time)
        bot.reply_to(message, f"✅ Got it! I'll remind you to *{task}* at {remind_time.strftime('%I:%M %p, %b %d')} IST", parse_mode="Markdown")
    else:
        bot.reply_to(message, "Try saying:\n'remind me every day at 8am to meditate'\nor 'remind me to call mom at 7pm'")


# --- Background Worker Thread ---
threading.Thread(target=check_reminders, daemon=True).start()

print("🤖 Bot running with recurring reminders, smart summaries, and IST timezone...")
bot.infinity_polling()
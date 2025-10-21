# reminder_bot.py
import telebot
import re
import time
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # Python 3.9+
import dateparser
from dateparser.search import search_dates
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


# === Database Helper Functions ===
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


# === Background Reminder Checker ===
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


# === Robust Parsing with explicit RELATIVE_BASE in IST ===
def parse_reminder_message(text):
    """
    Robust parser with explicit handling for 'tomorrow'/'today' and 'in N minutes/hours'.
    Returns dict with keys: ok, type, task, time (tz-aware IST), frequency (or None), error (if ok=False).
    """
    if not text or not text.strip():
        return {"ok": False, "error": "Empty message."}

    text_orig = text.strip()
    text_l = text_orig.lower().strip()

    # Use current IST time as the reference base for relative phrases
    relative_base = datetime.now(IST)
    dp_settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": "Asia/Kolkata",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "RELATIVE_BASE": relative_base
    }

    # Helper: try parsing a time-string, return tz-aware IST datetime or None
    def try_parse_time_fragment(fragment):
        # direct parse first
        dt = dateparser.parse(fragment, settings=dp_settings)
        if dt:
            return dt.astimezone(IST)
        # try search_dates on fragment
        res = search_dates(fragment, settings=dp_settings)
        if res:
            return res[-1][1].astimezone(IST)
        return None

    # 1) Recurring reminders: "remind me every day at 8am to meditate"
    recurring_match = re.search(r"remind me every (day|daily|week|weekly) at (.+?) to (.+)", text_l)
    if recurring_match:
        freq_raw = recurring_match.group(1)
        frequency = "daily" if "day" in freq_raw or "daily" in freq_raw else "weekly"
        time_text = recurring_match.group(2).strip()
        task = recurring_match.group(3).strip()

        dt = try_parse_time_fragment(time_text)
        if not dt:
            return {"ok": False, "error": "😅 I couldn't understand the time in that recurring reminder. Try: 'every day at 8am'."}
        return {"ok": True, "type": "recurring", "task": task, "time": dt, "frequency": frequency}

    # 2) Straight pattern: "remind me to <task> at/in/on <time>"
    simple_match = re.search(r"remind me to (.+?) (?:at|in|on) (.+)", text_l)
    if simple_match:
        task = simple_match.group(1).strip()
        time_text = simple_match.group(2).strip()

        # Special handling for "tomorrow" and "today" when dateparser fails
        if "tomorrow" in time_text or "tomorrow" in text_l:
            # parse the time part (remove 'tomorrow' to get the clock time, e.g., '11am')
            time_only = re.sub(r"\btomorrow\b", "", time_text, flags=re.IGNORECASE).strip()
            # if time_only empty, try parsing from whole text
            dt_time = try_parse_time_fragment(time_only) if time_only else None
            if not dt_time:
                # try to parse time_text as-is
                dt_time = try_parse_time_fragment(time_text)
            if not dt_time:
                # fallback: try to extract hh[:mm] am/pm via regex
                m = re.search(r"(\d{1,2}(:\d{2})?\s?(am|pm)?)", time_text, flags=re.IGNORECASE)
                if m:
                    parsed_clock = dateparser.parse(m.group(1), settings=dp_settings)
                    if parsed_clock:
                        dt_time = parsed_clock.astimezone(IST)
            if not dt_time:
                return {"ok": False, "error": "😅 I couldn't understand the time (e.g. '11am'). Try: 'tomorrow at 11am' or 'in 2 hours'."}
            # Build a 'tomorrow' date with parsed clock
            tomorrow_date = (relative_base + timedelta(days=1)).date()
            dt = datetime(
                year=tomorrow_date.year,
                month=tomorrow_date.month,
                day=tomorrow_date.day,
                hour=dt_time.hour,
                minute=dt_time.minute,
                tzinfo=IST
            )
            return {"ok": True, "type": "one-time", "task": task, "time": dt, "frequency": None}

        # Special handling for "today"
        if "today" in time_text or "today" in text_l:
            time_only = re.sub(r"\btoday\b", "", time_text, flags=re.IGNORECASE).strip()
            dt_time = try_parse_time_fragment(time_only) if time_only else None
            if not dt_time:
                dt_time = try_parse_time_fragment(time_text)
            if not dt_time:
                return {"ok": False, "error": "😅 I couldn't understand the time (e.g. '11am'). Try: 'today at 11am' or 'in 2 hours'."}
            today_date = relative_base.date()
            dt = datetime(
                year=today_date.year,
                month=today_date.month,
                day=today_date.day,
                hour=dt_time.hour,
                minute=dt_time.minute,
                tzinfo=IST
            )
            # if this datetime is in the past relative to base, move to next day (user likely meant next occurrence)
            if dt <= relative_base:
                dt = dt + timedelta(days=1)
            return {"ok": True, "type": "one-time", "task": task, "time": dt, "frequency": None}

        # Handling "in N minutes/hours" and other relative phrases — rely on dateparser with RELATIVE_BASE
        dt = try_parse_time_fragment(time_text)
        if not dt:
            # as final fallback try search_dates on full original text
            res = search_dates(text_orig, settings=dp_settings)
            if res:
                dt = res[-1][1].astimezone(IST)
                # remove date fragment to get task candidate
                date_text = res[-1][0]
                task_candidate = re.sub(re.escape(date_text), "", text_orig, flags=re.IGNORECASE).strip()
                task_candidate = re.sub(r"(?i)remind me( to| that)?", "", task_candidate, flags=re.IGNORECASE).strip()
                if not task_candidate:
                    return {"ok": False, "error": "I found the time but couldn't find the task. Try: 'remind me to call mom at 7pm'."}
                return {"ok": True, "type": "one-time", "task": task_candidate, "time": dt, "frequency": None}
            return {"ok": False, "error": "😅 I couldn't understand the time. Try: 'in 10 minutes' or 'at 8 pm'."}
        # success
        return {"ok": True, "type": "one-time", "task": task, "time": dt, "frequency": None}

    # 3) Flexible fallback using search_dates on whole sentence
    res = search_dates(text_orig, settings=dp_settings)
    if res:
        date_text, dt = res[-1]
        task_candidate = re.sub(re.escape(date_text), "", text_orig, flags=re.IGNORECASE).strip()
        task_candidate = re.sub(r"(?i)remind me( to| that)?", "", task_candidate, flags=re.IGNORECASE).strip()
        if not task_candidate:
            return {"ok": False, "error": "I found the time but not the task. Try: 'remind me to call mom at 7pm'."}
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        dt = dt.astimezone(IST)
        return {"ok": True, "type": "one-time", "task": task_candidate, "time": dt, "frequency": None}

    # Nothing matched
    return {"ok": False, "error": "I couldn't find a time in your message. Try: 'remind me to call mom at 7pm' or 'remind me in 10 minutes'."}

# === Telegram Handlers ===
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.reply_to(message, (
        "👋 Hey there! I’m your personal reminder bot.\n\n"
        "You can tell me things like:\n"
        "🕐 `remind me to drink water at 8 pm`\n"
        "🔁 `remind me every day at 8am to meditate`\n\n"
        "Commands:\n"
        "/list - show all reminders\n"
        "/list today - show today's reminders\n"
        "/list week - show this week's reminders\n"
        "/delete <id> - delete a reminder by its ID\n\n"
        "🕓 Timezone: *IST (Asia/Kolkata)*\n"
        "I'll remember and notify you at the right time!"
    ), parse_mode="Markdown")


@bot.message_handler(commands=["list"])
def handle_list(message):
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
        rec = f" (🔁 {r['frequency']})" if r.get("recurring") else ""
        lines.append(f"• ID {rid}: {task}{rec} — ⏰ {t} IST")

    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")


@bot.message_handler(commands=["delete"])
def handle_delete(message):
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
    text = message.text or ""
    parsed = parse_reminder_message(text)

    if not parsed.get("ok"):
        # give the specific error (time missing / task missing / parse failure)
        bot.reply_to(message, parsed.get("error") + "\n\nTry:\n'remind me every day at 8am to meditate'\nor\n'remind me to call mom at 7pm'")
        return

    if parsed["type"] == "recurring":
        add_reminder(message.chat.id, parsed["task"], parsed["time"], recurring=True, frequency=parsed["frequency"])
        bot.reply_to(message, f"✅ Got it! I'll remind you *{parsed['frequency']}* to *{parsed['task']}* at {parsed['time'].strftime('%I:%M %p')} IST ⏰", parse_mode="Markdown")
        return

    if parsed["type"] == "one-time":
        add_reminder(message.chat.id, parsed["task"], parsed["time"])
        bot.reply_to(message, f"✅ Got it! I'll remind you to *{parsed['task']}* at {parsed['time'].strftime('%I:%M %p, %b %d')} IST", parse_mode="Markdown")
        return


# === Background Thread ===
threading.Thread(target=check_reminders, daemon=True).start()

print("🤖 Bot running with RELATIVE_BASE=IST, improved parsing & recurring reminders...")
bot.infinity_polling()
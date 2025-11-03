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
from calendar import monthrange
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

# --- In-memory (optional) ---
# scheduled_timers = {}  # (not used — keeping polling approach)


# === Utility Helpers ===
def compute_next_annual_occurrence(month: int, day: int, time_of_day: str = "09:00"):
    """
    Return next occurrence as tz-aware IST datetime.
    time_of_day: "HH:MM" in 24h format (IST).
    Handles rollover to next year and clamps invalid day-of-month (e.g., Feb 30 -> Feb 28/29).
    """
    now_ist = datetime.now(IST)
    year = now_ist.year

    # clamp day to month's last day for the target year
    last_day = monthrange(year, month)[1]
    use_day = min(day, last_day)

    hour, minute = map(int, time_of_day.split(":"))
    dt_ist = datetime(year=year, month=month, day=use_day, hour=hour, minute=minute, tzinfo=IST)

    if dt_ist <= now_ist:
        # schedule for next year
        year += 1
        last_day_next = monthrange(year, month)[1]
        use_day = min(day, last_day_next)
        dt_ist = datetime(year=year, month=month, day=use_day, hour=hour, minute=minute, tzinfo=IST)

    return dt_ist


# === Database Helper Functions ===
def add_reminder(chat_id, task, remind_time, recurring=False, frequency=None):
    # Store in UTC for consistency
    utc_time = remind_time.astimezone(UTC)
    res = supabase.table("reminders").insert({
        "chat_id": chat_id,
        "task": task,
        "remind_time": utc_time.isoformat(),
        "recurring": recurring,
        "frequency": frequency,
        "created_at": datetime.now(UTC).isoformat()
    }).execute()
    print(f"💾 Saved reminder: {task} at {remind_time} IST | {utc_time} UTC")
    return res.data[0] if res and getattr(res, "data", None) else None


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
        try:
            due = get_due_reminders()
            for r in due:
                try:
                    bot.send_message(r["chat_id"], f"🔔 Reminder: {r['task']}")
                    # Handle recurring reminders
                    if r.get("recurring"):
                        freq = r.get("frequency", "daily")
                        remind_time_ist = datetime.fromisoformat(r["remind_time"]).astimezone(IST)
                        if freq == "daily":
                            next_time = remind_time_ist + timedelta(days=1)
                        elif freq == "weekly":
                            next_time = remind_time_ist + timedelta(weeks=1)
                        elif freq in ("yearly", "annual"):
                            # try to add 1 year safely (handle Feb 29)
                            try:
                                next_time = remind_time_ist.replace(year=remind_time_ist.year + 1)
                            except ValueError:
                                # fallback to Feb 28
                                next_time = remind_time_ist.replace(year=remind_time_ist.year + 1, month=2, day=28)
                        else:
                            next_time = remind_time_ist + timedelta(days=1)
                        update_reminder_time(r["id"], next_time)
                    else:
                        delete_reminder(r["id"])
                except Exception as e:
                    print(f"Error sending reminder: {e}")
        except Exception as e:
            print(f"Error in check_reminders loop: {e}")
        time.sleep(30)


# === Parsing Helpers & Normalization ===
def normalize_relative_position(s: str) -> str:
    """
    Move 'tomorrow'/'today' after the time for more consistent parsing:
    e.g. "tomorrow at 11am" -> "at 11am tomorrow"
    """
    s2 = s

    # Case: "<something> tomorrow at 11am" -> "<something> at 11am tomorrow"
    s2 = re.sub(r"\b(tomorrow|today)\s+at\s+(\d{1,2}(:\d{2})?\s*(am|pm)?)\b",
                r"at \2 \1", s2, flags=re.IGNORECASE)

    # Case: "<something> tomorrow 11am" -> "<something> at 11am tomorrow"
    s2 = re.sub(r"\b(tomorrow|today)\s+(\d{1,2}(:\d{2})?\s*(am|pm)?)\b",
                r"at \2 \1", s2, flags=re.IGNORECASE)

    # Leading relative day handling: "tomorrow at 11am to check" -> "at 11am tomorrow to check"
    s2 = re.sub(r"\b(tomorrow|today)\s+at\s+(\d{1,2}(:\d{2})?\s*(am|pm)?)(.*)",
                r"at \2 \1\5", s2, flags=re.IGNORECASE)

    # Leading relative day without 'at': "tomorrow 11am to check" -> "at 11am tomorrow to check"
    s2 = re.sub(r"\b(tomorrow|today)\s+(\d{1,2}(:\d{2})?\s*(am|pm)?)(.*)",
                r"at \2 \1\5", s2, flags=re.IGNORECASE)

    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2


def try_parse_time_fragment(fragment, relative_base):
    dp_settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": "Asia/Kolkata",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "RELATIVE_BASE": relative_base
    }
    dt = dateparser.parse(fragment, settings=dp_settings)
    if dt:
        return dt.astimezone(IST)
    res = search_dates(fragment, settings=dp_settings)
    if res:
        return res[-1][1].astimezone(IST)
    return None


def parse_reminder_message(text):
    """
    Robust parser with preprocessing to normalize phrases like:
      "tomorrow at 11 am"  -> "at 11 am tomorrow"
      "tomorrow 11 am"     -> "at 11 am tomorrow"
      "today 7pm"          -> "at 7pm today"
    Uses IST RELATIVE_BASE so 'tomorrow'/'today' resolve correctly.
    Returns dict: ok, type, task, time (tz-aware IST), frequency, error.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "Empty message."}

    text_orig = text.strip()
    normalized_text = normalize_relative_position(text_orig)
    text_l = normalized_text.lower().strip()

    # Use current IST time as RELATIVE_BASE
    relative_base = datetime.now(IST)

    # 1) Recurring reminders: "remind me every day at 8am to meditate"
    recurring_match = re.search(r"remind me every (day|daily|week|weekly) at (.+?) to (.+)", text_l)
    if recurring_match:
        freq_raw = recurring_match.group(1)
        frequency = "daily" if "day" in freq_raw or "daily" in freq_raw else "weekly"
        time_text = recurring_match.group(2).strip()
        task = recurring_match.group(3).strip()

        dt = try_parse_time_fragment(time_text, relative_base)
        if not dt:
            return {"ok": False, "error": "😅 I couldn't understand the time in that recurring reminder. Try: 'every day at 8am'."}
        return {"ok": True, "type": "recurring", "task": task, "time": dt, "frequency": frequency}

    # 2) Straight pattern: "remind me to <task> at/in/on <time>"
    simple_match = re.search(r"remind me to (.+?) (?:at|in|on) (.+)", text_l)
    if simple_match:
        task = simple_match.group(1).strip()
        time_text = simple_match.group(2).strip()

        # Handle explicit "tomorrow"/"today" and other relative phrases using try_parse_time_fragment
        dt = try_parse_time_fragment(time_text, relative_base)
        if not dt:
            # fallback: search_dates on whole normalized text
            res = search_dates(normalized_text, settings={
                "PREFER_DATES_FROM": "future",
                "TIMEZONE": "Asia/Kolkata",
                "RETURN_AS_TIMEZONE_AWARE": True,
                "RELATIVE_BASE": relative_base
            })
            if res:
                dt = res[-1][1].astimezone(IST)
                date_text = res[-1][0]
                task_candidate = re.sub(re.escape(date_text), "", normalized_text, flags=re.IGNORECASE).strip()
                task_candidate = re.sub(r"(?i)remind me( to| that)?", "", task_candidate, flags=re.IGNORECASE).strip()
                if task_candidate:
                    task = task_candidate

        if not dt:
            return {"ok": False, "error": "😅 I couldn't understand the time. Try: 'in 10 minutes' or 'at 8 pm'."}
        return {"ok": True, "type": "one-time", "task": task, "time": dt, "frequency": None}

    # 3) Flexible fallback: detect date/time anywhere in sentence
    res = search_dates(normalized_text, settings={
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": "Asia/Kolkata",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "RELATIVE_BASE": relative_base
    })
    if res:
        date_text, dt = res[-1]
        task_candidate = re.sub(re.escape(date_text), "", normalized_text, flags=re.IGNORECASE).strip()
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
        rec = f" (🔁 {r['frequency']})" if r.get("recurring") else ""
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
    """
    Handles both natural-language reminders and birthday sentences.
    Birthday creation is done via natural language only (no commands).
    """
    text = message.text or ""
    text_l = text.lower()

    # --- Birthday detection (natural language only) ---
    # Look for keyword 'birthday' or "born" and attempt to parse a date and name
    if "birthday" in text_l or "born" in text_l:
        # Use RELATIVE_BASE=IST for consistent "today/tomorrow" parsing
        relative_base = datetime.now(IST)
        dp_settings = {
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "Asia/Kolkata",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "RELATIVE_BASE": relative_base
        }

        res = search_dates(text, settings=dp_settings)
        if not res:
            # fallback: sometimes users say "John's birthday is Oct 12" -> parse month/day tokens
            # simple heuristic: find "<name>'s birthday on Oct 12"
            m = re.search(r"([A-Za-z][A-Za-z ']+?)['’]?s birthday(?: on)? (.+)", text, flags=re.IGNORECASE)
            if m:
                name_candidate = m.group(1).strip()
                date_fragment = m.group(2).strip()
                dt = dateparser.parse(date_fragment, settings=dp_settings)
                if dt:
                    res = [(date_fragment, dt)]
            # else not recognized

        if res:
            date_text, dt = res[-1]
            # extract name: remove the date_text and 'birthday' and common words
            name_candidate = re.sub(re.escape(date_text), "", text, flags=re.IGNORECASE)
            name_candidate = re.sub(r"(?i)birthday|born|on|remember|add|for|my|the|is|it's|it is", "", name_candidate, flags=re.IGNORECASE).strip()
            # if still empty, prompt user
            if not name_candidate:
                bot.reply_to(message, "Who is this birthday for? Try: `Remember John's birthday on Oct 12`")
                return
            # Normalize name (first letter caps)
            name_candidate = " ".join([w.capitalize() for w in name_candidate.split()])[:80]

            # get month/day/time from dt (ensure IST tz)
            dt_ist = dt.astimezone(IST) if dt.tzinfo else dt.replace(tzinfo=IST)
            month = dt_ist.month
            day = dt_ist.day
            time_of_day = dt_ist.strftime("%H:%M")

            # compute next occurrence in IST and create a yearly recurring reminder
            next_ist = compute_next_annual_occurrence(month, day, time_of_day)
            # add_reminder will store as UTC and set recurring/yearly
            add_reminder(message.chat.id, f"{name_candidate}'s birthday", next_ist, recurring=True, frequency="yearly")
            bot.reply_to(message, f"🎉 Got it — I'll remind you of *{name_candidate}*'s birthday on {day:02d}/{month:02d} at {time_of_day} IST (next: {next_ist.strftime('%I:%M %p, %b %d')}).", parse_mode="Markdown")
            return
        else:
            # If we couldn't parse a date, ask a clarifying question
            bot.reply_to(message, "I see you mentioned a birthday but couldn't find the date. Try: `Remember John's birthday on Oct 12` or `John's birthday is on 12 Oct at 09:00`")
            return

    # --- Otherwise, handle general reminder parsing/creation ---
    parsed = parse_reminder_message(text)
    if not parsed.get("ok"):
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


# --- Start background checker and bot polling ---
threading.Thread(target=check_reminders, daemon=True).start()

print("🤖 Bot running with natural-language birthday support (yearly reminders) and IST timezone...")
bot.infinity_polling()
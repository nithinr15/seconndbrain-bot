# bot/parser.py
import re
import dateparser
from dateparser.search import search_dates
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

def normalize_relative_position(s: str) -> str:
    s2 = s
    s2 = re.sub(r"\b(tomorrow|today)\s+at\s+(\d{1,2}(:\d{2})?\s*(am|pm)?)\b",
                r"at \2 \1", s2, flags=re.IGNORECASE)
    s2 = re.sub(r"\b(tomorrow|today)\s+(\d{1,2}(:\d{2})?\s*(am|pm)?)\b",
                r"at \2 \1", s2, flags=re.IGNORECASE)
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2

def try_parse_time_fragment(fragment: str, relative_base: datetime):
    dp_settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": "Asia/Kolkata",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "RELATIVE_BASE": relative_base,
    }
    dt = dateparser.parse(fragment, settings=dp_settings)
    if dt:
        return dt.astimezone(IST)
    res = search_dates(fragment, settings=dp_settings)
    if res:
        return res[-1][1].astimezone(IST)
    return None

def parse_reminder_message(text: str):
    """
    Returns dict:
      {ok, type, task, time (tz-aware IST), frequency, error}
    """
    if not text or not text.strip():
        return {"ok": False, "error": "Empty message."}

    text_orig = text.strip()
    normalized = normalize_relative_position(text_orig)
    text_l = normalized.lower()
    relative_base = datetime.now(IST)

    # recurring pattern
    recurring_match = re.search(r"remind me every (day|daily|week|weekly) at (.+?) to (.+)", text_l)
    if recurring_match:
        freq_raw = recurring_match.group(1)
        frequency = "daily" if "day" in freq_raw or "daily" in freq_raw else "weekly"
        time_text = recurring_match.group(2).strip()
        task = recurring_match.group(3).strip()
        dt = try_parse_time_fragment(time_text, relative_base)
        if not dt:
            return {"ok": False, "error": "I couldn't understand the time in that recurring reminder."}
        return {"ok": True, "type": "recurring", "task": task, "time": dt, "frequency": frequency}

    # simple one-time
    simple_match = re.search(r"remind me to (.+?) (?:at|in|on) (.+)", text_l)
    if simple_match:
        task = simple_match.group(1).strip()
        time_text = simple_match.group(2).strip()
        dt = try_parse_time_fragment(time_text, relative_base)
        if not dt:
            # fallback search in whole text
            res = search_dates(normalized, settings={
                "PREFER_DATES_FROM": "future",
                "TIMEZONE": "Asia/Kolkata",
                "RETURN_AS_TIMEZONE_AWARE": True,
                "RELATIVE_BASE": relative_base,
            })
            if res:
                dt = res[-1][1].astimezone(IST)
        if not dt:
            return {"ok": False, "error": "I couldn't understand the time. Try: 'in 10 minutes' or 'at 8 pm'."}
        return {"ok": True, "type": "one-time", "task": task, "time": dt, "frequency": None}

    # fallback: search anywhere in sentence
    res = search_dates(normalized, settings={
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": "Asia/Kolkata",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "RELATIVE_BASE": relative_base,
    })
    if res:
        date_text, dt = res[-1]
        task_candidate = re.sub(re.escape(date_text), "", normalized, flags=re.IGNORECASE).strip()
        task_candidate = re.sub(r"(?i)remind me( to| that)?", "", task_candidate, flags=re.IGNORECASE).strip()
        if not task_candidate:
            return {"ok": False, "error": "Found time but couldn't find the task."}
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        dt = dt.astimezone(IST)
        return {"ok": True, "type": "one-time", "task": task_candidate, "time": dt, "frequency": None}

    return {"ok": False, "error": "I couldn't find a time in your message."}
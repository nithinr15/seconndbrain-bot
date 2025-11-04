# bot/db.py
from supabase import create_client, Client
from datetime import datetime
from zoneinfo import ZoneInfo
import os

UTC = ZoneInfo("UTC")

class DB:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    def add_reminder(self, chat_id, task, remind_time, recurring=False, frequency=None):
        utc_time = remind_time.astimezone(UTC)
        res = self.client.table("reminders").insert({
            "chat_id": chat_id,
            "task": task,
            "remind_time": utc_time.isoformat(),
            "recurring": recurring,
            "frequency": frequency,
            "created_at": datetime.now(UTC).isoformat()
        }).execute()
        return res.data[0] if res and getattr(res, "data", None) else None

    def get_due_reminders(self):
        now = datetime.now(UTC).isoformat()
        data = self.client.table("reminders").select("*").lte("remind_time", now).execute()
        return data.data if data.data else []

    def delete_reminder(self, rid):
        self.client.table("reminders").delete().eq("id", rid).execute()

    def update_reminder_time(self, rid, new_time):
        utc_time = new_time.astimezone(UTC)
        self.client.table("reminders").update({"remind_time": utc_time.isoformat()}).eq("id", rid).execute()

    def get_user_reminders(self, chat_id):
        data = self.client.table("reminders").select("*").eq("chat_id", chat_id).order("remind_time", desc=False).execute()
        return data.data if data.data else []
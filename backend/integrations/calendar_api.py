"""
Google Calendar API 串接模組
Gemma 4 透過 function calling 操作 Calendar
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# ── Function Calling Schema（供 GemmaClient 使用）────────────────────────────

CALENDAR_TOOLS = [
    {
        "name": "create_review_event",
        "description": "在 Google Calendar 建立一個複習事件",
        "parameters": {
            "type": "object",
            "properties": {
                "title":             {"type": "string",  "description": "知識點名稱，例如：遞迴 — 第2輪"},
                "start_datetime":    {"type": "string",  "description": "ISO 8601 格式，例如：2026-04-15T20:00:00+08:00"},
                "duration_minutes":  {"type": "integer", "description": "預計複習分鐘數，建議 15–30"},
                "blind_spot_id":     {"type": "string",  "description": "對應的盲點 ID，用於後續追蹤"},
            },
            "required": ["title", "start_datetime", "duration_minutes"],
        },
    },
    {
        "name": "get_free_slots",
        "description": "查詢指定日期範圍內的行程空檔",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date":           {"type": "string",  "description": "YYYY-MM-DD"},
                "end_date":             {"type": "string",  "description": "YYYY-MM-DD"},
                "min_duration_minutes": {"type": "integer", "default": 20},
            },
            "required": ["start_date", "end_date"],
        },
    },
]


# ── API 操作 ─────────────────────────────────────────────────────────────────

def _get_service(credentials_dict: dict):
    creds = Credentials(
        token=credentials_dict["access_token"],
        refresh_token=credentials_dict.get("refresh_token"),
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("calendar", "v3", credentials=creds)


async def create_review_event(
    credentials_dict: dict,
    title: str,
    start_datetime: str,
    duration_minutes: int,
    blind_spot_id: str = "",
) -> dict[str, Any]:
    """在 Google Calendar 建立複習事件"""
    import asyncio
    service = _get_service(credentials_dict)
    start = datetime.fromisoformat(start_datetime)
    end = start + timedelta(minutes=duration_minutes)

    event = {
        "summary": f"📚 複習：{title}",
        "description": f"RecallMap 自動排程\n盲點 ID：{blind_spot_id}" if blind_spot_id else "RecallMap 自動排程",
        "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Taipei"},
        "end":   {"dateTime": end.isoformat(),   "timeZone": "Asia/Taipei"},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 5}]},
    }

    # Google API 是同步的，用 asyncio.to_thread 包裝
    result = await asyncio.to_thread(
        service.events().insert(calendarId="primary", body=event).execute
    )
    return {"event_id": result.get("id"), "html_link": result.get("htmlLink")}


async def get_free_slots(
    credentials_dict: dict,
    start_date: str,
    end_date: str,
    min_duration_minutes: int = 20,
) -> list[dict]:
    """查詢行程空檔"""
    import asyncio
    service = _get_service(credentials_dict)

    time_min = f"{start_date}T00:00:00+08:00"
    time_max = f"{end_date}T23:59:59+08:00"

    events_result = await asyncio.to_thread(
        service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute
    )
    busy_events = events_result.get("items", [])

    # 簡單計算空檔：每天 08:00–22:00，扣掉已有行程
    free_slots = []
    current = datetime.fromisoformat(f"{start_date}T08:00:00+08:00")
    end_dt = datetime.fromisoformat(f"{end_date}T22:00:00+08:00")

    busy_times = []
    for evt in busy_events:
        s = evt.get("start", {}).get("dateTime")
        e = evt.get("end", {}).get("dateTime")
        if s and e:
            busy_times.append((datetime.fromisoformat(s), datetime.fromisoformat(e)))

    while current < end_dt:
        day_end = current.replace(hour=22, minute=0, second=0)
        slot_start = current
        for busy_start, busy_end in sorted(busy_times):
            if busy_start >= day_end:
                break
            if busy_end <= slot_start:
                continue
            # 空檔在 busy 之前
            if slot_start < busy_start:
                gap = (busy_start - slot_start).total_seconds() / 60
                if gap >= min_duration_minutes:
                    free_slots.append({"start": slot_start, "end": busy_start})
            slot_start = max(slot_start, busy_end)

        # 當天剩餘空檔
        if slot_start < day_end:
            gap = (day_end - slot_start).total_seconds() / 60
            if gap >= min_duration_minutes:
                free_slots.append({"start": slot_start, "end": day_end})

        # 跳到下一天 08:00
        current = (current + timedelta(days=1)).replace(hour=8, minute=0, second=0)

    return [{"start": s["start"].isoformat(), "end": s["end"].isoformat()} for s in free_slots]

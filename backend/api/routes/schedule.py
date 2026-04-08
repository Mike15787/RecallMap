"""
POST /v1/schedules — 建立複習排程並寫入 Google Calendar
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.store import session_store

router = APIRouter()


class ScheduleRequest(BaseModel):
    session_id: str
    exam_date: str | None = None        # ISO 8601 日期字串


@router.post("")
async def create_schedule(body: ScheduleRequest):
    sess = await session_store.get_or_404(body.session_id)

    if not sess["blind_spots"]:
        raise HTTPException(status_code=422, detail="尚未偵測到盲點，請先取得學習地圖")

    credentials = sess.get("calendar_credentials")
    if not credentials:
        raise HTTPException(
            status_code=403,
            detail="尚未連接 Google Calendar，請先完成 /v1/auth/google 授權",
        )

    exam_date = None
    if body.exam_date:
        try:
            exam_date = datetime.fromisoformat(body.exam_date)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"無效的考試日期格式：{body.exam_date}")

    from backend.engine.scheduler import build_review_schedule
    from backend.integrations.calendar_api import get_free_slots, create_review_event

    # 取得行程空檔
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    end_day = (exam_date or datetime.now(tz=timezone.utc)).strftime("%Y-%m-%d")
    try:
        free_slots_raw = await get_free_slots(credentials, today, end_day)
        free_slots = [
            {"start": datetime.fromisoformat(s["start"]), "end": datetime.fromisoformat(s["end"])}
            for s in free_slots_raw
        ]
    except Exception:
        free_slots = None   # fallback：不考慮空檔

    events = build_review_schedule(sess["blind_spots"], exam_date, free_slots)

    created = []
    for ev in events:
        try:
            result = await create_review_event(
                credentials_dict=credentials,
                title=f"{ev.concept} — 第{ev.round_number}輪",
                start_datetime=ev.suggested_start.isoformat(),
                duration_minutes=ev.duration_minutes,
                blind_spot_id=ev.blind_spot_id,
            )
            created.append({**result, "concept": ev.concept, "round": ev.round_number})
        except Exception as e:
            created.append({"concept": ev.concept, "round": ev.round_number, "error": str(e)})

    return {"scheduled": len(created), "events": created}

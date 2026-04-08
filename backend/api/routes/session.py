"""
POST /v1/sessions — 建立新的學習 session
GET  /v1/sessions/{id} — 查詢 session 資訊
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.store import session_store

router = APIRouter()


class CreateSessionRequest(BaseModel):
    subject: str | None = None          # 科目名稱（選填）
    exam_date: str | None = None        # 考試日期 ISO 8601（選填）


class SessionResponse(BaseModel):
    session_id: str
    created_at: str
    subject: str | None
    exam_date: str | None
    status: str


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(body: CreateSessionRequest):
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    now = datetime.now(tz=timezone.utc).isoformat()
    await session_store.create(
        session_id=session_id,
        created_at=now,
        subject=body.subject,
        exam_date=body.exam_date,
    )
    return SessionResponse(
        session_id=session_id,
        created_at=now,
        subject=body.subject,
        exam_date=body.exam_date,
        status="active",
    )


@router.get("/{session_id}")
async def get_session(session_id: str):
    sess = await session_store.get_or_404(session_id)
    return {
        "session_id": sess["session_id"],
        "created_at": sess["created_at"],
        "subject": sess["subject"],
        "exam_date": sess["exam_date"],
        "status": sess["status"],
        "chunk_count": len(sess["chunks"]),
        "blind_spot_count": len(sess["blind_spots"]),
    }

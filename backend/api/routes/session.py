"""
POST /v1/sessions — 建立新的學習 session
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# 簡易記憶體 store（之後可換成 Redis 或 SQLite）
_sessions: dict[str, dict] = {}


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
    _sessions[session_id] = {
        "session_id": session_id,
        "created_at": now,
        "subject": body.subject,
        "exam_date": body.exam_date,
        "status": "active",
        "chunks": [],
        "blind_spots": [],
        "learning_map": None,
        "dialogue_sessions": {},
        "calendar_credentials": None,
    }
    return SessionResponse(
        session_id=session_id,
        created_at=now,
        subject=body.subject,
        exam_date=body.exam_date,
        status="active",
    )


@router.get("/{session_id}")
async def get_session(session_id: str):
    sess = _get_or_404(session_id)
    return {
        "session_id": sess["session_id"],
        "created_at": sess["created_at"],
        "subject": sess["subject"],
        "exam_date": sess["exam_date"],
        "status": sess["status"],
        "chunk_count": len(sess["chunks"]),
        "blind_spot_count": len(sess["blind_spots"]),
    }


def _get_or_404(session_id: str) -> dict:
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session 不存在：{session_id}")
    return sess


def get_session_store() -> dict[str, dict]:
    return _sessions

"""
SQLite 持久化 Session Store

替代原本的記憶體 dict，重啟後資料不消失。
DB 路徑由環境變數 DATABASE_PATH 控制（預設 ./recallmap.db）。

Session dict 結構（在記憶體中流通的 Python 物件）：
{
    "session_id": str,
    "created_at": str,
    "subject": str | None,
    "exam_date": str | None,
    "status": str,
    "chunks": list[DocumentChunk],
    "blind_spots": list[BlindSpot],
    "learning_map": dict | None,        # LearningMap.to_dict() 的結果
    "dialogue_sessions": dict,          # blind_spot_id → DialogueSession
    "calendar_credentials": dict | None,
}
"""
import json
import os
from typing import Any

import aiosqlite
from fastapi import HTTPException

_DB_PATH = os.environ.get("DATABASE_PATH", "./recallmap.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id              TEXT PRIMARY KEY,
    created_at              TEXT NOT NULL,
    subject                 TEXT,
    exam_date               TEXT,
    status                  TEXT NOT NULL DEFAULT 'active',
    chunks_json             TEXT NOT NULL DEFAULT '[]',
    blind_spots_json        TEXT NOT NULL DEFAULT '[]',
    learning_map_json       TEXT,
    dialogue_sessions_json  TEXT NOT NULL DEFAULT '{}',
    calendar_credentials_json TEXT
)
"""


# ── 序列化工具 ────────────────────────────────────────────────────────────────

def _serialize_session(sess: dict) -> dict:
    """把 Python 物件轉成可存入 SQLite 的 JSON 字串 dict"""
    from backend.ingest.base import DocumentChunk
    from backend.engine.blind_spot import BlindSpot
    from backend.engine.dialogue import DialogueSession

    def chunk_to_dict(c: DocumentChunk) -> dict:
        return {
            "content": c.content,
            "source_type": c.source_type.value,
            "source_id": c.source_id,
            "metadata": c.metadata,
            "is_conversation": c.is_conversation,
            "language": c.language,
        }

    def spot_to_dict(s: BlindSpot) -> dict:
        return {
            "concept": s.concept,
            "confidence": s.confidence,
            "evidence": s.evidence,
            "repeat_count": s.repeat_count,
            "blind_spot_id": s.blind_spot_id,
        }

    def dial_sess_to_dict(ds: DialogueSession) -> dict:
        return {
            "session_id": ds.session_id,
            "blind_spot_id": ds.blind_spot_id,
            "concept": ds.concept,
            "turns": [{"role": t.role, "content": t.content} for t in ds.turns],
            "final_confidence": ds.final_confidence,
            "is_completed": ds.is_completed,
        }

    return {
        "chunks_json": json.dumps([chunk_to_dict(c) for c in sess.get("chunks", [])], ensure_ascii=False),
        "blind_spots_json": json.dumps([spot_to_dict(s) for s in sess.get("blind_spots", [])], ensure_ascii=False),
        "learning_map_json": json.dumps(sess["learning_map"], ensure_ascii=False) if sess.get("learning_map") else None,
        "dialogue_sessions_json": json.dumps(
            {k: dial_sess_to_dict(v) for k, v in sess.get("dialogue_sessions", {}).items()},
            ensure_ascii=False,
        ),
        "calendar_credentials_json": json.dumps(sess["calendar_credentials"], ensure_ascii=False)
        if sess.get("calendar_credentials") else None,
    }


def _deserialize_session(row: dict) -> dict:
    """把 SQLite row 還原成帶有 Python 物件的 session dict"""
    from backend.ingest.base import DocumentChunk, SourceType
    from backend.engine.blind_spot import BlindSpot
    from backend.engine.dialogue import DialogueSession, DialogueTurn

    def dict_to_chunk(d: dict) -> DocumentChunk:
        return DocumentChunk(
            content=d["content"],
            source_type=SourceType(d["source_type"]),
            source_id=d["source_id"],
            metadata=d.get("metadata", {}),
            is_conversation=d.get("is_conversation", False),
            language=d.get("language", "zh-TW"),
        )

    def dict_to_spot(d: dict) -> BlindSpot:
        return BlindSpot(
            concept=d["concept"],
            confidence=d["confidence"],
            evidence=d.get("evidence", []),
            repeat_count=d.get("repeat_count", 0),
            blind_spot_id=d.get("blind_spot_id", ""),
        )

    def dict_to_dial_sess(d: dict) -> DialogueSession:
        ds = DialogueSession(
            session_id=d["session_id"],
            blind_spot_id=d["blind_spot_id"],
            concept=d["concept"],
            final_confidence=d.get("final_confidence"),
            is_completed=d.get("is_completed", False),
        )
        ds.turns = [DialogueTurn(role=t["role"], content=t["content"]) for t in d.get("turns", [])]
        return ds

    chunks = [dict_to_chunk(c) for c in json.loads(row["chunks_json"] or "[]")]
    blind_spots = [dict_to_spot(s) for s in json.loads(row["blind_spots_json"] or "[]")]
    learning_map = json.loads(row["learning_map_json"]) if row["learning_map_json"] else None
    dial_raw: dict[str, Any] = json.loads(row["dialogue_sessions_json"] or "{}")
    dialogue_sessions = {k: dict_to_dial_sess(v) for k, v in dial_raw.items()}
    calendar_credentials = json.loads(row["calendar_credentials_json"]) if row["calendar_credentials_json"] else None

    return {
        "session_id": row["session_id"],
        "created_at": row["created_at"],
        "subject": row["subject"],
        "exam_date": row["exam_date"],
        "status": row["status"],
        "chunks": chunks,
        "blind_spots": blind_spots,
        "learning_map": learning_map,
        "dialogue_sessions": dialogue_sessions,
        "calendar_credentials": calendar_credentials,
    }


# ── SessionStore ──────────────────────────────────────────────────────────────

class SessionStore:
    """SQLite 持久化 session store，所有方法皆為 async。"""

    def __init__(self, db_path: str = _DB_PATH) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """建立資料表（應用啟動時呼叫一次）"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    async def create(
        self,
        session_id: str,
        created_at: str,
        subject: str | None,
        exam_date: str | None,
    ) -> dict:
        """建立新 session，回傳完整 session dict"""
        sess: dict = {
            "session_id": session_id,
            "created_at": created_at,
            "subject": subject,
            "exam_date": exam_date,
            "status": "active",
            "chunks": [],
            "blind_spots": [],
            "learning_map": None,
            "dialogue_sessions": {},
            "calendar_credentials": None,
        }
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO sessions
                   (session_id, created_at, subject, exam_date, status,
                    chunks_json, blind_spots_json, learning_map_json,
                    dialogue_sessions_json, calendar_credentials_json)
                   VALUES (?, ?, ?, ?, 'active', '[]', '[]', NULL, '{}', NULL)""",
                (session_id, created_at, subject, exam_date),
            )
            await db.commit()
        return sess

    async def get(self, session_id: str) -> dict | None:
        """回傳 session dict，找不到回傳 None"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return _deserialize_session(dict(row))

    async def get_or_404(self, session_id: str) -> dict:
        """回傳 session dict，找不到拋 404"""
        sess = await self.get(session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail=f"Session 不存在：{session_id}")
        return sess

    async def save(self, sess: dict) -> None:
        """將 session dict 序列化後寫回 SQLite"""
        serialized = _serialize_session(sess)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE sessions SET
                   subject = ?,
                   exam_date = ?,
                   status = ?,
                   chunks_json = ?,
                   blind_spots_json = ?,
                   learning_map_json = ?,
                   dialogue_sessions_json = ?,
                   calendar_credentials_json = ?
                   WHERE session_id = ?""",
                (
                    sess.get("subject"),
                    sess.get("exam_date"),
                    sess.get("status", "active"),
                    serialized["chunks_json"],
                    serialized["blind_spots_json"],
                    serialized["learning_map_json"],
                    serialized["dialogue_sessions_json"],
                    serialized["calendar_credentials_json"],
                    sess["session_id"],
                ),
            )
            await db.commit()


# 全域單例，所有 route 共用
session_store = SessionStore()

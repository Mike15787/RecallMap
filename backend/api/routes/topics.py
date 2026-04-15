"""
/v1/topics — 知識庫主題管理 + 雙軸掌握度 + 意圖管理
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────────────

class ClassifyRequest(BaseModel):
    session_id: str


class IntentRequest(BaseModel):
    intent: Literal["active", "snoozed", "archived"]
    snooze_until: str | None = None   # ISO 8601


class ComprehensionAnswerRequest(BaseModel):
    question_type: str
    question: str
    user_answer: str
    is_delayed_test: bool = False


class RetentionAnswerRequest(BaseModel):
    question_type: str
    question: str
    user_answer: str
    correct_answer: str


# ── 主題列表 ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_topics():
    """GET /v1/topics — 取得知識庫所有主題"""
    from backend.engine import knowledge_base as kb
    topics = await kb.get_topics()
    return [
        {
            "topic_id": t.topic_id,
            "name": t.name,
            "description": t.description,
            "language": t.language,
            "created_at": t.created_at.isoformat(),
        }
        for t in topics
    ]


@router.post("/{topic_id}/classify")
async def classify_topic(topic_id: str, body: ClassifyRequest):
    """
    POST /v1/topics/{id}/classify
    將指定 session 的 chunks 分類至此主題（或更新現有主題）。
    """
    from backend.api.store import session_store
    from backend.engine import topic_classifier

    sess = await session_store.get_or_404(body.session_id)
    chunks = sess.get("chunks", [])
    if not chunks:
        raise HTTPException(status_code=422, detail="Session 沒有 chunks，請先上傳學習材料")

    clusters = await topic_classifier.classify(chunks)
    return {
        "topics_created": sum(1 for c in clusters if c.is_new),
        "topics_merged": sum(1 for c in clusters if not c.is_new),
        "clusters": [
            {
                "topic_id": c.topic_id,
                "topic_name": c.topic_name,
                "is_new": c.is_new,
                "chunk_count": len(c.chunk_ids),
            }
            for c in clusters
        ],
    }


# ── 掌握度（雙軸）────────────────────────────────────────────────────────────

@router.get("/{topic_id}/mastery")
async def get_topic_mastery(topic_id: str):
    """GET /v1/topics/{id}/mastery — 取得主題下所有概念的掌握度摘要"""
    from backend.db.connection import get_db

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM mastery_records WHERE topic_id = ? ORDER BY comprehension_score ASC",
            (topic_id,),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    return {
        "topic_id": topic_id,
        "concept_count": len(rows),
        "concepts": [
            {
                "concept_id": r["concept_id"],
                "concept_name": r["concept_name"],
                "comprehension_score": r["comprehension_score"],
                "comprehension_level": r["comprehension_level"],
                "retention_score": r["retention_score"],
                "next_review_due": r["next_review_due"],
                "pending_confirmation": bool(r["pending_confirmation"]),
                "intent": r["intent"],
            }
            for r in rows
        ],
    }


# ── 概念操作 ──────────────────────────────────────────────────────────────────

@router.get("/concepts/{concept_id}/mastery")
async def get_concept_mastery(concept_id: str):
    """GET /v1/topics/concepts/{id}/mastery — 取得單一概念完整掌握度"""
    from backend.engine import knowledge_base as kb
    try:
        record = await kb.get_mastery(concept_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"概念不存在：{concept_id}")

    return _mastery_to_dict(record)


@router.post("/concepts/{concept_id}/comprehension")
async def record_comprehension(concept_id: str, body: ComprehensionAnswerRequest):
    """
    POST /v1/topics/concepts/{id}/comprehension
    記錄理解型事件，更新理解軸。
    """
    from backend.engine import comprehension_engine
    try:
        result = await comprehension_engine.evaluate_answer(
            concept_id=concept_id,
            question_type=body.question_type,
            user_answer=body.user_answer,
            question=body.question,
            is_delayed_test=body.is_delayed_test,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"概念不存在：{concept_id}")

    pending_msg = None
    if result.updated_record.pending_confirmation and not body.is_delayed_test:
        pending_msg = "✳️ 初步確認，明天再來驗證！"

    return {
        "verdict": result.gemma_verdict,
        "reasoning": result.gemma_reasoning,
        "score_delta": result.score_delta,
        "comprehension_score": result.updated_record.comprehension_score,
        "comprehension_level": result.updated_record.comprehension_level,
        "pending_confirmation": result.updated_record.pending_confirmation,
        "pending_message": pending_msg,
    }


@router.post("/concepts/{concept_id}/retention")
async def record_retention(concept_id: str, body: RetentionAnswerRequest):
    """
    POST /v1/topics/concepts/{id}/retention
    記錄記憶型事件，更新記憶軸（SM-2）。
    """
    from backend.engine import retention_engine
    try:
        result = await retention_engine.evaluate_answer(
            concept_id=concept_id,
            question_type=body.question_type,
            user_answer=body.user_answer,
            correct_answer=body.correct_answer,
            question=body.question,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"概念不存在：{concept_id}")

    next_due = result.updated_record.next_review_due
    return {
        "response_quality": result.response_quality,
        "retention_score": result.updated_record.retention_score,
        "sm2_interval": result.updated_record.sm2_interval,
        "next_review_due": next_due.isoformat() if next_due else None,
    }


@router.post("/concepts/{concept_id}/confirm")
async def confirm_delayed(concept_id: str):
    """
    POST /v1/topics/concepts/{id}/confirm
    觸發延遲確認，升級 comprehension_level。
    """
    from backend.engine import knowledge_base as kb
    try:
        record = await kb.confirm_delayed(concept_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"概念不存在：{concept_id}")

    return {
        "concept_id": concept_id,
        "comprehension_level": record.comprehension_level,
        "comprehension_score": record.comprehension_score,
        "pending_confirmation": record.pending_confirmation,
    }


@router.patch("/concepts/{concept_id}/intent")
async def set_intent(concept_id: str, body: IntentRequest):
    """
    PATCH /v1/topics/concepts/{id}/intent
    設定概念意圖（active / snoozed / archived）。
    """
    from backend.engine import knowledge_base as kb
    snooze_until = None
    if body.snooze_until:
        try:
            snooze_until = datetime.fromisoformat(body.snooze_until)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"snooze_until 格式錯誤：{body.snooze_until}")

    try:
        record = await kb.set_intent(concept_id, body.intent, snooze_until)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"概念不存在：{concept_id}")

    return {
        "concept_id": concept_id,
        "intent": record.intent,
        "snooze_until": record.snooze_until.isoformat() if record.snooze_until else None,
    }


# ── Session 觸發器 ────────────────────────────────────────────────────────────

@router.get("/session/next")
async def get_next_session():
    """GET /v1/topics/session/next — 回傳下次建議的複習清單"""
    from backend.engine import session_trigger
    plan = await session_trigger.build_session()

    return {
        "generated_at": plan.generated_at.isoformat(),
        "has_pending_confirmations": plan.has_pending_confirmations,
        "item_count": len(plan.items),
        "items": [
            {
                "concept_id": item.concept_id,
                "concept_name": item.concept_name,
                "topic_id": item.topic_id,
                "priority": item.priority,
                "comprehension_score": item.comprehension_score,
                "retention_score": item.retention_score,
                "next_review_due": item.next_review_due.isoformat() if item.next_review_due else None,
                "pending_confirmation": item.pending_confirmation,
            }
            for item in plan.items
        ],
    }


# ── 內部工具 ──────────────────────────────────────────────────────────────────

def _mastery_to_dict(record) -> dict:
    return {
        "concept_id": record.concept_id,
        "topic_id": record.topic_id,
        "concept_name": record.concept_name,
        "comprehension_score": record.comprehension_score,
        "comprehension_level": record.comprehension_level,
        "last_comprehension_test": record.last_comprehension_test.isoformat() if record.last_comprehension_test else None,
        "pending_confirmation": record.pending_confirmation,
        "retention_score": record.retention_score,
        "sm2_interval": record.sm2_interval,
        "next_review_due": record.next_review_due.isoformat() if record.next_review_due else None,
        "intent": record.intent,
        "snooze_until": record.snooze_until.isoformat() if record.snooze_until else None,
    }

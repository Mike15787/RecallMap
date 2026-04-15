"""
延遲確認機制 — 流暢幻覺（Fluency Illusion）防護
RUNTIME: edge（純邏輯，不呼叫 AI）

當天 deep 回答 → 設 pending_confirmation=True + 時間戳
24h 後延遲測驗通過 → confirm_delayed() 觸發真正升級

此模組負責：
  1. 掃描所有 pending_confirmation=True 且超過 24h 的概念
  2. 生成延遲測驗題目（委由 comprehension_engine）
  3. 測驗通過後呼叫 knowledge_base.confirm_delayed()
"""
import logging
from datetime import datetime, timedelta, timezone

from backend.db.connection import get_db
from backend.engine import knowledge_base as kb

logger = logging.getLogger(__name__)

CONFIRMATION_DELAY_HOURS = 24


async def get_pending_concepts() -> list[kb.MasteryRecord]:
    """
    回傳所有超過 24h 等待確認的概念（pending_confirmation=True）。
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=CONFIRMATION_DELAY_HOURS)).isoformat()

    async with get_db() as db:
        async with db.execute(
            """SELECT concept_id FROM mastery_records
               WHERE pending_confirmation = 1
               AND pending_since IS NOT NULL
               AND pending_since <= ?
               ORDER BY pending_since ASC""",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()

    records: list[kb.MasteryRecord] = []
    for row in rows:
        try:
            records.append(await kb.get_mastery(row["concept_id"]))
        except KeyError:
            pass
    return records


async def run_delayed_test(
    concept_id: str,
    user_answer: str,
    question: str,
    question_type: str,
) -> kb.MasteryRecord:
    """
    執行延遲測驗評估。
    通過（verdict=deep/solid）→ 呼叫 confirm_delayed() 升級；否則清除 pending 標記。
    """
    from backend.engine import comprehension_engine

    result = await comprehension_engine.evaluate_answer(
        concept_id=concept_id,
        question_type=question_type,
        user_answer=user_answer,
        question=question,
        is_delayed_test=True,
    )

    if result.gemma_verdict in ("deep", "solid"):
        logger.info(f"[delayed_confirmation] 延遲測驗通過：{concept_id}，升級 comprehension_level")
        return await kb.confirm_delayed(concept_id)
    else:
        # 測驗未通過，清除 pending 標記（等下次 deep 回答再重設）
        logger.info(f"[delayed_confirmation] 延遲測驗未通過：{concept_id}，清除 pending 標記")
        await _clear_pending(concept_id)
        return result.updated_record


async def _clear_pending(concept_id: str) -> None:
    from datetime import timezone
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE mastery_records SET pending_confirmation=0, pending_since=NULL, updated_at=? WHERE concept_id=?",
            (now, concept_id),
        )
        await db.commit()

"""
使用者意圖層 — 管理概念的 Active / Snoozed / Archived 狀態
RUNTIME: edge（純邏輯）

狀態說明：
  active   — 正常參與複習排程
  snoozed  — 暫停，支援無期限 + 指定喚醒日期；背景遺忘曲線持續衰減
  archived — 永久封存，不出現在排程（仍保留歷史紀錄）

喚醒流程：
  Snoozed 到期 → 自動轉回 active，附上重新定向摘要 + 首個 session 預覽
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from backend.engine import knowledge_base as kb
from backend.db.connection import get_db

logger = logging.getLogger(__name__)

IntentType = Literal["active", "snoozed", "archived"]


# ── 資料類別 ──────────────────────────────────────────────────────────────────

@dataclass
class WakeupSummary:
    concept_id: str
    concept_name: str
    snoozed_since: datetime | None
    comprehension_score: float
    retention_score: float
    message: str               # 重新定向摘要，顯示給使用者


# ── 公開介面 ──────────────────────────────────────────────────────────────────

async def snooze(
    concept_id: str,
    until: datetime | None = None,
) -> kb.MasteryRecord:
    """
    暫停概念。until=None → 無期限；until=datetime → 指定喚醒日期。
    """
    return await kb.set_intent(concept_id, "snoozed", until)


async def unsnooze(concept_id: str) -> kb.MasteryRecord:
    """手動喚醒（將 snoozed → active，清除 snooze_until）"""
    return await kb.set_intent(concept_id, "active", None)


async def archive(concept_id: str) -> kb.MasteryRecord:
    """封存概念（active/snoozed → archived）"""
    return await kb.set_intent(concept_id, "archived", None)


async def check_and_wake_snoozed() -> list[WakeupSummary]:
    """
    掃描所有 snoozed 概念，自動喚醒到期的概念（snooze_until <= now）。
    回傳被喚醒的概念的喚醒摘要列表。
    """
    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        async with db.execute(
            """SELECT concept_id, snooze_until FROM mastery_records
               WHERE intent = 'snoozed'
               AND snooze_until IS NOT NULL
               AND snooze_until <= ?""",
            (now,),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    summaries: list[WakeupSummary] = []
    for row in rows:
        concept_id = row["concept_id"]
        try:
            record = await kb.get_mastery(concept_id)
            snoozed_since = record.snooze_until

            await kb.set_intent(concept_id, "active", None)
            updated = await kb.get_mastery(concept_id)

            summary = _build_wakeup_summary(updated, snoozed_since)
            summaries.append(summary)
            logger.info(f"[intent_layer] 自動喚醒：{concept_id}（{updated.concept_name}）")
        except Exception as e:
            logger.warning(f"[intent_layer] 喚醒失敗 {concept_id}：{e}")

    return summaries


async def get_by_intent(intent: IntentType) -> list[kb.MasteryRecord]:
    """回傳指定意圖的所有概念掌握度記錄"""
    async with get_db() as db:
        async with db.execute(
            "SELECT concept_id FROM mastery_records WHERE intent = ? ORDER BY updated_at DESC",
            (intent,),
        ) as cur:
            rows = await cur.fetchall()

    records: list[kb.MasteryRecord] = []
    for row in rows:
        try:
            records.append(await kb.get_mastery(row["concept_id"]))
        except KeyError:
            pass
    return records


# ── 內部函式 ──────────────────────────────────────────────────────────────────

def _build_wakeup_summary(record: kb.MasteryRecord, snoozed_since: datetime | None) -> WakeupSummary:
    comp_pct = int(record.comprehension_score * 100)
    retention_pct = int(record.retention_score * 100)

    if record.comprehension_score < 0.3:
        msg = f"「{record.concept_name}」還有很多需要理解的地方（{comp_pct}%），建議先從基礎問題開始。"
    elif record.retention_score < 0.5:
        msg = f"「{record.concept_name}」你有一定理解（{comp_pct}%），但記憶可能已衰減，先做幾道複習題暖身吧。"
    else:
        msg = f"「{record.concept_name}」理解 {comp_pct}%、記憶 {retention_pct}%，繼續保持！"

    return WakeupSummary(
        concept_id=record.concept_id,
        concept_name=record.concept_name,
        snoozed_since=snoozed_since,
        comprehension_score=record.comprehension_score,
        retention_score=record.retention_score,
        message=msg,
    )

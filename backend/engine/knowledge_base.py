"""
知識庫 — SQLite 持久化主題與掌握度管理
RUNTIME: edge（純邏輯，不直接呼叫 AI；find_similar_topic 例外，用 Gemma 語意比對）

公開介面（全部 async）：
  get_topics() → list[Topic]
  find_similar_topic(name) → Topic | None
  add_topic(name, description, language) → Topic
  add_chunks_to_topic(topic_id, chunks) → None
  get_chunks_by_topic(topic_id) → ChunkList
  get_mastery(concept_id) → MasteryRecord
  get_or_create_mastery(topic_id, concept_id, concept_name) → MasteryRecord
  update_comprehension(concept_id, event) → MasteryRecord
  update_retention(concept_id, event) → MasteryRecord
  confirm_delayed(concept_id) → MasteryRecord
  set_intent(concept_id, intent, snooze_until) → MasteryRecord
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from backend.db.connection import get_db
from backend.ingest.base import ChunkList, DocumentChunk, SourceType

logger = logging.getLogger(__name__)

# ── 資料類別 ──────────────────────────────────────────────────────────────────

@dataclass
class Topic:
    topic_id: str
    name: str
    description: str
    language: str
    created_at: datetime


@dataclass
class ComprehensionEvent:
    timestamp: datetime
    question_type: str        # explain / apply / analogy / debug
    user_answer: str
    gemma_verdict: str        # no_understanding / partial / solid / deep
    gemma_reasoning: str
    score_delta: float
    is_delayed_test: bool


@dataclass
class RetentionEvent:
    timestamp: datetime
    question_type: str        # cloze / multiple_choice / true_false
    response_quality: int     # SM-2：0–5
    new_interval: int
    new_easiness: float


ComprehensionLevel = Literal["none", "surface", "deep", "transferable"]
IntentType = Literal["active", "snoozed", "archived"]


@dataclass
class MasteryRecord:
    concept_id: str
    topic_id: str
    concept_name: str

    # ── 理解軸 ──
    comprehension_score: float = 0.0
    comprehension_level: ComprehensionLevel = "none"
    last_comprehension_test: datetime | None = None
    pending_confirmation: bool = False
    pending_since: datetime | None = None
    comprehension_history: list[ComprehensionEvent] = field(default_factory=list)

    # ── 記憶軸 ──
    retention_score: float = 0.0
    sm2_interval: int = 1
    sm2_repetitions: int = 0
    sm2_ease_factor: float = 2.5
    last_retention_test: datetime | None = None
    next_review_due: datetime | None = None
    retention_history: list[RetentionEvent] = field(default_factory=list)

    # ── 使用者意圖 ──
    intent: IntentType = "active"
    snooze_until: datetime | None = None


# ── 內部工具 ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    return datetime.fromisoformat(val)


def _row_to_mastery(row: dict, c_events: list[dict], r_events: list[dict]) -> MasteryRecord:
    """SQLite row + events → MasteryRecord dataclass"""
    c_history = [
        ComprehensionEvent(
            timestamp=datetime.fromisoformat(e["timestamp"]),
            question_type=e["question_type"],
            user_answer=e["user_answer"],
            gemma_verdict=e["gemma_verdict"],
            gemma_reasoning=e["gemma_reasoning"],
            score_delta=e["score_delta"],
            is_delayed_test=bool(e["is_delayed_test"]),
        )
        for e in c_events
    ]
    r_history = [
        RetentionEvent(
            timestamp=datetime.fromisoformat(e["timestamp"]),
            question_type=e["question_type"],
            response_quality=e["response_quality"],
            new_interval=e["new_interval"],
            new_easiness=e["new_easiness"],
        )
        for e in r_events
    ]
    return MasteryRecord(
        concept_id=row["concept_id"],
        topic_id=row["topic_id"],
        concept_name=row["concept_name"],
        comprehension_score=row["comprehension_score"],
        comprehension_level=row["comprehension_level"],
        last_comprehension_test=_parse_dt(row["last_comprehension_test"]),
        pending_confirmation=bool(row["pending_confirmation"]),
        pending_since=_parse_dt(row["pending_since"]),
        comprehension_history=c_history,
        retention_score=row["retention_score"],
        sm2_interval=row["sm2_interval"],
        sm2_repetitions=row["sm2_repetitions"],
        sm2_ease_factor=row["sm2_ease_factor"],
        last_retention_test=_parse_dt(row["last_retention_test"]),
        next_review_due=_parse_dt(row["next_review_due"]),
        retention_history=r_history,
        intent=row["intent"],
        snooze_until=_parse_dt(row["snooze_until"]),
    )


def _level_from_score(score: float) -> ComprehensionLevel:
    """依分數換算理解層級（僅用於初始建立，升級靠 confirm_delayed）"""
    if score >= 0.8:
        return "transferable"
    if score >= 0.5:
        return "deep"
    if score >= 0.2:
        return "surface"
    return "none"


_LEVEL_ORDER: list[ComprehensionLevel] = ["none", "surface", "deep", "transferable"]


def _next_level(current: ComprehensionLevel) -> ComprehensionLevel:
    idx = _LEVEL_ORDER.index(current)
    return _LEVEL_ORDER[min(idx + 1, len(_LEVEL_ORDER) - 1)]


# ── 公開介面 ──────────────────────────────────────────────────────────────────

async def get_topics() -> list[Topic]:
    """回傳知識庫所有主題"""
    async with get_db() as db:
        async with db.execute(
            "SELECT topic_id, name, description, language, created_at FROM topics ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [
        Topic(
            topic_id=r["topic_id"],
            name=r["name"],
            description=r["description"],
            language=r["language"],
            created_at=datetime.fromisoformat(r["created_at"]),
        )
        for r in rows
    ]


async def find_similar_topic(name: str) -> Topic | None:
    """
    找到語意相似的已知主題（先文字比對，再 Gemma 語意判斷）。
    回傳最相似的 Topic，或 None（無相似主題）。
    """
    topics = await get_topics()
    if not topics:
        return None

    # 1. 完全或部分文字比對（快速路徑）
    name_lower = name.lower()
    for t in topics:
        if name_lower == t.name.lower() or name_lower in t.name.lower() or t.name.lower() in name_lower:
            return t

    # 2. Gemma 語意相似度判斷（慢速路徑）
    if len(topics) > 0:
        from backend.engine.gemma_client import GemmaClient
        client = GemmaClient()
        candidates = [t.name for t in topics]
        prompt = (
            f"你是學習知識庫管理員。\n"
            f"新主題：「{name}」\n"
            f"現有主題列表：{json.dumps(candidates, ensure_ascii=False)}\n\n"
            f"判斷「{name}」是否與列表中的某個主題語意相同（例如中英文同義、縮寫展開）。\n"
            f"若有，只回傳完全相同的主題名稱；若無，回傳 null。\n"
            f"只能回傳 JSON 格式，例如：{{\"match\": \"Python 列表推導式\"}} 或 {{\"match\": null}}"
        )
        try:
            raw = await client.generate(prompt, mode="edge")
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                matched_name = data.get("match")
                if matched_name:
                    for t in topics:
                        if t.name == matched_name:
                            return t
        except Exception as e:
            logger.warning(f"[knowledge_base] Gemma 語意比對失敗，跳過：{e}")

    return None


async def add_topic(
    name: str,
    description: str = "",
    language: str = "zh-TW",
) -> Topic:
    """在知識庫新增主題，回傳 Topic"""
    topic_id = str(uuid.uuid4())
    now = _now_iso()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO topics (topic_id, name, description, language, created_at) VALUES (?, ?, ?, ?, ?)",
            (topic_id, name, description, language, now),
        )
        await db.commit()
    return Topic(topic_id=topic_id, name=name, description=description, language=language, created_at=datetime.fromisoformat(now))


async def add_chunks_to_topic(topic_id: str, chunks: ChunkList) -> None:
    """將 DocumentChunk 列表儲存到指定主題"""
    async with get_db() as db:
        for chunk in chunks:
            await db.execute(
                """INSERT INTO topic_chunks
                   (topic_id, content, source_type, source_id, metadata, is_conversation, language)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    topic_id,
                    chunk.content,
                    chunk.source_type.value,
                    chunk.source_id,
                    json.dumps(chunk.metadata, ensure_ascii=False),
                    int(chunk.is_conversation),
                    chunk.language,
                ),
            )
        await db.commit()


async def get_chunks_by_topic(topic_id: str) -> ChunkList:
    """回傳主題下所有 DocumentChunk"""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM topic_chunks WHERE topic_id = ? ORDER BY id",
            (topic_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [
        DocumentChunk(
            content=r["content"],
            source_type=SourceType(r["source_type"]),
            source_id=r["source_id"],
            metadata=json.loads(r["metadata"]),
            is_conversation=bool(r["is_conversation"]),
            language=r["language"],
        )
        for r in rows
    ]


async def get_mastery(concept_id: str) -> MasteryRecord:
    """
    取得概念掌握度（含完整事件歷史）。
    若不存在拋 KeyError。
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM mastery_records WHERE concept_id = ?", (concept_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"掌握度記錄不存在：{concept_id}")

        async with db.execute(
            "SELECT * FROM comprehension_events WHERE concept_id = ? ORDER BY timestamp",
            (concept_id,),
        ) as cur:
            c_rows = [dict(r) for r in await cur.fetchall()]

        async with db.execute(
            "SELECT * FROM retention_events WHERE concept_id = ? ORDER BY timestamp",
            (concept_id,),
        ) as cur:
            r_rows = [dict(r) for r in await cur.fetchall()]

    return _row_to_mastery(dict(row), c_rows, r_rows)


async def get_or_create_mastery(
    topic_id: str,
    concept_id: str,
    concept_name: str,
) -> MasteryRecord:
    """若掌握度記錄不存在則建立並回傳"""
    try:
        return await get_mastery(concept_id)
    except KeyError:
        now = _now_iso()
        async with get_db() as db:
            await db.execute(
                """INSERT OR IGNORE INTO mastery_records
                   (concept_id, topic_id, concept_name, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (concept_id, topic_id, concept_name, now, now),
            )
            await db.commit()
        return await get_mastery(concept_id)


async def update_comprehension(
    concept_id: str,
    event: ComprehensionEvent,
) -> MasteryRecord:
    """
    記錄理解型事件，依 verdict 更新 comprehension_score 和 pending_confirmation。

    分數規則：
      deep（延遲測驗）→ 不改分，由 confirm_delayed() 處理升級
      deep（當天）    → +0.10，設 pending_confirmation = True
      solid           → +0.05
      partial         → +0.02
      no_understanding→ -0.15
    """
    record = await get_mastery(concept_id)

    verdict = event.gemma_verdict
    is_delayed = event.is_delayed_test

    if verdict == "deep" and is_delayed:
        score_delta = 0.0  # confirm_delayed() 才真正升級
    elif verdict == "deep":
        score_delta = 0.10
    elif verdict == "solid":
        score_delta = 0.05
    elif verdict == "partial":
        score_delta = 0.02
    else:  # no_understanding
        score_delta = -0.15

    new_score = max(0.0, min(1.0, record.comprehension_score + score_delta))
    pending = record.pending_confirmation
    pending_since = record.pending_since
    now = _now_iso()

    if verdict == "deep" and not is_delayed:
        pending = True
        pending_since = now

    # 寫入事件 + 更新 mastery
    async with get_db() as db:
        await db.execute(
            """INSERT INTO comprehension_events
               (concept_id, timestamp, question_type, user_answer,
                gemma_verdict, gemma_reasoning, score_delta, is_delayed_test)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                concept_id,
                event.timestamp.isoformat(),
                event.question_type,
                event.user_answer,
                event.gemma_verdict,
                event.gemma_reasoning,
                score_delta,
                int(event.is_delayed_test),
            ),
        )
        await db.execute(
            """UPDATE mastery_records SET
               comprehension_score = ?,
               last_comprehension_test = ?,
               pending_confirmation = ?,
               pending_since = ?,
               updated_at = ?
               WHERE concept_id = ?""",
            (new_score, event.timestamp.isoformat(), int(pending), pending_since, now, concept_id),
        )
        await db.commit()

    return await get_mastery(concept_id)


async def update_retention(
    concept_id: str,
    event: RetentionEvent,
) -> MasteryRecord:
    """
    記錄記憶型事件，執行 SM-2 演算法更新。
    response_quality < 2 → comprehension_score ×= 0.95（輕微連動衰減）。
    """
    record = await get_mastery(concept_id)
    q = event.response_quality

    # SM-2
    if q >= 3:
        reps = record.sm2_repetitions + 1
        if reps == 1:
            new_interval = 1
        elif reps == 2:
            new_interval = 6
        else:
            new_interval = round(record.sm2_interval * record.sm2_ease_factor)
    else:
        reps = 0
        new_interval = 1

    ease = record.sm2_ease_factor + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
    new_ease = max(1.3, ease)

    # 記憶分：用 response_quality 換算 0–1
    retention_score = max(0.0, min(1.0, q / 5.0))

    # 連動衰減
    comp_score = record.comprehension_score
    if q < 2:
        comp_score = max(0.0, comp_score * 0.95)

    from datetime import timedelta
    next_due = (datetime.now(timezone.utc) + timedelta(days=new_interval)).isoformat()
    now = _now_iso()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO retention_events
               (concept_id, timestamp, question_type, response_quality, new_interval, new_easiness)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                concept_id,
                event.timestamp.isoformat(),
                event.question_type,
                event.response_quality,
                new_interval,
                new_ease,
            ),
        )
        await db.execute(
            """UPDATE mastery_records SET
               retention_score = ?,
               sm2_interval = ?,
               sm2_repetitions = ?,
               sm2_ease_factor = ?,
               last_retention_test = ?,
               next_review_due = ?,
               comprehension_score = ?,
               updated_at = ?
               WHERE concept_id = ?""",
            (
                retention_score,
                new_interval,
                reps,
                new_ease,
                event.timestamp.isoformat(),
                next_due,
                comp_score,
                now,
                concept_id,
            ),
        )
        await db.commit()

    return await get_mastery(concept_id)


async def confirm_delayed(concept_id: str) -> MasteryRecord:
    """
    24h 延遲測驗通過，真正觸發 comprehension_level 升一級，清除 pending 標記。
    """
    record = await get_mastery(concept_id)
    if not record.pending_confirmation:
        return record  # 無待確認，直接回傳

    new_level = _next_level(record.comprehension_level)
    now = _now_iso()

    async with get_db() as db:
        await db.execute(
            """UPDATE mastery_records SET
               comprehension_level = ?,
               pending_confirmation = 0,
               pending_since = NULL,
               updated_at = ?
               WHERE concept_id = ?""",
            (new_level, now, concept_id),
        )
        await db.commit()

    return await get_mastery(concept_id)


async def set_intent(
    concept_id: str,
    intent: IntentType,
    snooze_until: datetime | None = None,
) -> MasteryRecord:
    """設定概念的使用者意圖（active / snoozed / archived）"""
    now = _now_iso()
    snooze_str = snooze_until.isoformat() if snooze_until else None

    async with get_db() as db:
        await db.execute(
            """UPDATE mastery_records SET
               intent = ?, snooze_until = ?, updated_at = ?
               WHERE concept_id = ?""",
            (intent, snooze_str, now, concept_id),
        )
        await db.commit()

    return await get_mastery(concept_id)

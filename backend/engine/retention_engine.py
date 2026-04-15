"""
記憶軸引擎 — SM-2 間隔複習出題與評分
RUNTIME: auto（Gemma 出題；SM-2 為純演算法）

題型：cloze（填空）/ multiple_choice（選擇）/ true_false（是非）
Interleaving：同主題 3–5 個相關概念交錯出題，防止「集中練習幻覺」
記憶未通過 → comprehension_score × 0.95 輕微連動衰減（由 knowledge_base 處理）
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.db.connection import get_db
from backend.engine.gemma_client import GemmaClient
from backend.engine import knowledge_base as kb

logger = logging.getLogger(__name__)

# ── 資料類別 ──────────────────────────────────────────────────────────────────

@dataclass
class RetentionQuestion:
    concept_id: str
    concept_name: str
    question_type: str          # cloze / multiple_choice / true_false
    question: str
    options: list[str] | None = None   # MCQ 四選項
    correct_answer: str = ""           # 後端用，不回傳前端
    hint: str = ""


@dataclass
class RetentionResult:
    concept_id: str
    question_type: str
    response_quality: int       # 0–5
    updated_record: kb.MasteryRecord


# ── 公開介面 ──────────────────────────────────────────────────────────────────

async def generate_question(
    concept_id: str,
    interleave_with: list[str] | None = None,
) -> RetentionQuestion:
    """
    生成記憶型題目。
    interleave_with: 其他概念 ID 列表，用於交錯出題（可選）。
    """
    record = await kb.get_mastery(concept_id)
    chunks = await kb.get_chunks_by_topic(record.topic_id)
    q_type = _select_question_type(record.sm2_interval, record.sm2_repetitions)

    return await _generate(record, chunks, q_type, interleave_with or [])


async def evaluate_answer(
    concept_id: str,
    question_type: str,
    user_answer: str,
    correct_answer: str,
    question: str,
) -> RetentionResult:
    """
    評估記憶型答案，計算 response_quality（0–5）並更新 SM-2。
    """
    quality = _score_answer(question_type, user_answer, correct_answer)

    event = kb.RetentionEvent(
        timestamp=datetime.now(timezone.utc),
        question_type=question_type,
        response_quality=quality,
        new_interval=1,    # 由 knowledge_base.update_retention 重新計算
        new_easiness=2.5,  # 同上
    )

    updated = await kb.update_retention(concept_id, event)

    return RetentionResult(
        concept_id=concept_id,
        question_type=question_type,
        response_quality=quality,
        updated_record=updated,
    )


async def get_interleave_batch(topic_id: str, count: int = 5) -> list[str]:
    """
    取得同主題下 3–5 個適合交錯出題的概念 ID（按 next_review_due 排序）。
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT concept_id FROM mastery_records
               WHERE topic_id = ? AND intent = 'active'
               ORDER BY next_review_due ASC NULLS FIRST
               LIMIT ?""",
            (topic_id, count),
        ) as cur:
            rows = await cur.fetchall()
    return [r["concept_id"] for r in rows]


# ── 內部函式 ──────────────────────────────────────────────────────────────────

def _select_question_type(sm2_interval: int, repetitions: int) -> str:
    """依 SM-2 狀態選擇題型：初期 → 填空；中期 → 選擇；穩固 → 是非"""
    if repetitions <= 1:
        return "cloze"
    elif repetitions <= 3:
        return "multiple_choice"
    else:
        return "true_false"


def _score_answer(q_type: str, user_answer: str, correct_answer: str) -> int:
    """將使用者答案換算成 SM-2 response_quality（0–5）"""
    if not user_answer.strip():
        return 0

    user_norm = user_answer.strip().lower()
    correct_norm = correct_answer.strip().lower()

    if q_type == "true_false":
        return 5 if user_norm == correct_norm else 0

    # 選擇題：完全比對
    if q_type == "multiple_choice":
        return 5 if user_norm == correct_norm else 1

    # 填空：模糊比對（包含正確答案關鍵字）
    if q_type == "cloze":
        key_words = [w for w in correct_norm.split() if len(w) > 1]
        hits = sum(1 for kw in key_words if kw in user_norm)
        ratio = hits / max(len(key_words), 1)
        if ratio >= 0.9:
            return 5
        elif ratio >= 0.7:
            return 4
        elif ratio >= 0.5:
            return 3
        elif ratio >= 0.3:
            return 2
        elif ratio > 0:
            return 1
        return 0

    return 3  # fallback


async def _generate(
    record: kb.MasteryRecord,
    chunks: list,
    q_type: str,
    interleave_ids: list[str],
) -> RetentionQuestion:
    client = GemmaClient()
    context = "\n\n".join(c.content[:600] for c in chunks[:4])
    if len(context) > 2000:
        context = context[:2000] + "\n...(已截斷)"

    # 交錯提示
    interleave_hint = ""
    if interleave_ids:
        try:
            other_names = []
            for cid in interleave_ids[:3]:
                if cid != record.concept_id:
                    r = await kb.get_mastery(cid)
                    other_names.append(r.concept_name)
            if other_names:
                interleave_hint = f"（可適當結合以下相關概念出題：{', '.join(other_names)}）"
        except Exception:
            pass

    type_prompt = {
        "cloze": "生成一道填空題，在關鍵詞或關鍵概念處留空（用 ___ 表示）",
        "multiple_choice": "生成一道四選一選擇題（A/B/C/D），測試核心知識點",
        "true_false": "生成一道是非題（陳述句，回答「是」或「否」）",
    }

    prompt = (
        f"你是記憶複習出題系統。\n\n"
        f"概念：「{record.concept_name}」{interleave_hint}\n"
        f"參考材料：\n{context}\n\n"
        f"題型指示：{type_prompt.get(q_type, type_prompt['cloze'])}\n\n"
        f"確保題目無法靠短期記憶或猜測作答，必須真正記憶才能回答。\n"
        f"只回傳嚴格 JSON：\n"
        f"填空/是非：{{\"question\": \"...\", \"correct_answer\": \"...\", \"hint\": \"...\"}}\n"
        f"選擇題：{{\"question\": \"...\", \"options\": [\"A...\", \"B...\", \"C...\", \"D...\"], \"correct_answer\": \"A\", \"hint\": \"\"}}"
    )

    try:
        raw = await client.generate(prompt, mode="auto")
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return RetentionQuestion(
                concept_id=record.concept_id,
                concept_name=record.concept_name,
                question_type=q_type,
                question=data.get("question", ""),
                options=data.get("options"),
                correct_answer=data.get("correct_answer", ""),
                hint=data.get("hint", ""),
            )
    except Exception as e:
        logger.warning(f"[retention_engine] 出題失敗：{e}")

    return RetentionQuestion(
        concept_id=record.concept_id,
        concept_name=record.concept_name,
        question_type="true_false",
        question=f"「{record.concept_name}」是本學習材料中的核心概念。（是/否）",
        correct_answer="是",
    )

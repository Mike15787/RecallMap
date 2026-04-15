"""
理解軸引擎 — 理解深度評估與題目生成
RUNTIME: auto（Gemma 深層判斷）

題型策略（依 comprehension_score）：
  完全不懂（< 0.2）  → explain（請解釋...）
  部分理解（0.2–0.5）→ apply（應用題）/ analogy（類比題）
  接近掌握（> 0.5）  → debug（錯誤分析）/ apply（遷移題）

評分（gemma_verdict）：
  no_understanding / partial / solid / deep

流暢幻覺防護：
  deep 回答僅設 pending_confirmation=True，
  需 24h 後延遲測驗通過才真正升級（由 delayed_confirmation.py 處理）。
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.engine.gemma_client import GemmaClient
from backend.engine import knowledge_base as kb

logger = logging.getLogger(__name__)

# ── 資料類別 ──────────────────────────────────────────────────────────────────

@dataclass
class ComprehensionQuestion:
    concept_id: str
    concept_name: str
    question_type: str      # explain / apply / analogy / debug
    question: str
    hint: str = ""


@dataclass
class ComprehensionResult:
    concept_id: str
    question_type: str
    user_answer: str
    gemma_verdict: str      # no_understanding / partial / solid / deep
    gemma_reasoning: str
    score_delta: float
    updated_record: kb.MasteryRecord


# ── 公開介面 ──────────────────────────────────────────────────────────────────

async def generate_question(
    concept_id: str,
) -> ComprehensionQuestion:
    """
    根據概念當前的 comprehension_score 選擇題型並生成問題。
    """
    record = await kb.get_mastery(concept_id)
    chunks = await kb.get_chunks_by_topic(record.topic_id)
    q_type = _select_question_type(record.comprehension_score)

    return await _generate(record, chunks, q_type)


async def evaluate_answer(
    concept_id: str,
    question_type: str,
    user_answer: str,
    question: str,
    is_delayed_test: bool = False,
) -> ComprehensionResult:
    """
    用 Gemma 評估使用者的理解型答案，更新掌握度。
    """
    record = await kb.get_mastery(concept_id)
    chunks = await kb.get_chunks_by_topic(record.topic_id)
    context = _build_context(chunks)

    verdict, reasoning = await _evaluate(
        concept_name=record.concept_name,
        question=question,
        question_type=question_type,
        user_answer=user_answer,
        context=context,
    )

    score_delta = _verdict_to_delta(verdict, is_delayed_test)

    event = kb.ComprehensionEvent(
        timestamp=datetime.now(timezone.utc),
        question_type=question_type,
        user_answer=user_answer,
        gemma_verdict=verdict,
        gemma_reasoning=reasoning,
        score_delta=score_delta,
        is_delayed_test=is_delayed_test,
    )

    updated = await kb.update_comprehension(concept_id, event)

    return ComprehensionResult(
        concept_id=concept_id,
        question_type=question_type,
        user_answer=user_answer,
        gemma_verdict=verdict,
        gemma_reasoning=reasoning,
        score_delta=score_delta,
        updated_record=updated,
    )


# ── 內部函式 ──────────────────────────────────────────────────────────────────

def _select_question_type(score: float) -> str:
    if score < 0.2:
        return "explain"
    elif score < 0.5:
        return "apply"
    elif score < 0.8:
        return "analogy"
    else:
        return "debug"


def _build_context(chunks: list) -> str:
    combined = "\n\n".join(c.content[:800] for c in chunks[:5])
    if len(combined) > 2000:
        combined = combined[:2000] + "\n...(已截斷)"
    return combined


async def _generate(
    record: kb.MasteryRecord,
    chunks: list,
    q_type: str,
) -> ComprehensionQuestion:
    client = GemmaClient()
    context = _build_context(chunks)

    type_desc = {
        "explain": "請要求學生用自己的話解釋這個概念（不能直接背誦定義）",
        "apply":   "請設計一個需要應用此概念的實際問題（給出具體情境）",
        "analogy": "請要求學生用類比或比喻解釋此概念，並說明相似之處",
        "debug":   "請設計一個含有概念性錯誤的例子，讓學生找出並修正",
    }

    prompt = (
        f"你是學習助理，正在幫助學生理解「{record.concept_name}」。\n\n"
        f"相關學習材料摘要：\n{context}\n\n"
        f"學生目前的理解分數：{record.comprehension_score:.2f}（0=完全不懂，1=完全掌握）\n"
        f"題型指示：{type_desc.get(q_type, type_desc['explain'])}\n\n"
        f"請生成一道適合此學生程度的問題。\n"
        f"回傳嚴格 JSON：{{\"question\": \"...\", \"hint\": \"...\"}}\n"
        f"（hint 為選填提示，如不需要則為空字串）"
    )

    try:
        raw = await client.generate(prompt, mode="auto")
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return ComprehensionQuestion(
                concept_id=record.concept_id,
                concept_name=record.concept_name,
                question_type=q_type,
                question=data.get("question", ""),
                hint=data.get("hint", ""),
            )
    except Exception as e:
        logger.warning(f"[comprehension_engine] 題目生成失敗：{e}")

    # Fallback
    return ComprehensionQuestion(
        concept_id=record.concept_id,
        concept_name=record.concept_name,
        question_type=q_type,
        question=f"請用你自己的話解釋「{record.concept_name}」的核心概念。",
        hint="",
    )


async def _evaluate(
    concept_name: str,
    question: str,
    question_type: str,
    user_answer: str,
    context: str,
) -> tuple[str, str]:
    """呼叫 Gemma 評估答案，回傳 (verdict, reasoning)"""
    client = GemmaClient()

    prompt = (
        f"你是嚴格但公正的學習評估者。\n\n"
        f"概念：「{concept_name}」\n"
        f"題型：{question_type}\n"
        f"題目：{question}\n"
        f"學生答案：{user_answer}\n\n"
        f"參考材料（用來判斷答案是否正確）：\n{context[:1500]}\n\n"
        f"評估標準：\n"
        f"  deep          — 完整理解且能舉一反三，無法靠短期記憶套答\n"
        f"  solid         — 理解核心概念，有小瑕疵但方向正確\n"
        f"  partial       — 部分理解，有明顯誤解或缺漏\n"
        f"  no_understanding — 答非所問或完全不理解\n\n"
        f"只回傳嚴格 JSON：{{\"verdict\": \"deep|solid|partial|no_understanding\", \"reasoning\": \"一句話解釋\"}}"
    )

    try:
        raw = await client.generate(prompt, mode="auto")
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            verdict = data.get("verdict", "partial")
            reasoning = data.get("reasoning", "")
            if verdict in ("deep", "solid", "partial", "no_understanding"):
                return verdict, reasoning
    except Exception as e:
        logger.warning(f"[comprehension_engine] 評估失敗：{e}")

    return "partial", "評估系統暫時無法回應，預設為部分理解"


def _verdict_to_delta(verdict: str, is_delayed_test: bool) -> float:
    if verdict == "deep" and is_delayed_test:
        return 0.0   # confirm_delayed() 處理
    elif verdict == "deep":
        return 0.10
    elif verdict == "solid":
        return 0.05
    elif verdict == "partial":
        return 0.02
    else:
        return -0.15

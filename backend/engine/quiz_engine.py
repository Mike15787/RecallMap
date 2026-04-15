"""
Domain-Aware 自適應測驗引擎
RUNTIME: auto（Gemma 出題 + domain 偵測）

三步驟：
  1. Domain 偵測（math_formula / programming / language / memorization / calculation）
  2. 題型選擇（依 domain + comprehension_score + QuizStrategy）
  3. 完整題目生成（含 domain 專用欄位）

Gemma 回傳嚴格 JSON → 後端直接 parse 對應 Quiz dataclass。
correct_answer 僅後端保留，不回傳前端。
"""
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from backend.engine.gemma_client import GemmaClient
from backend.engine import knowledge_base as kb

logger = logging.getLogger(__name__)


# ── Enum & 資料類別 ──────────────────────────────────────────────────────────

class QuestionType(str, Enum):
    SHORT_ANSWER    = "short_answer"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE      = "true_false"
    FILL_BLANK      = "fill_blank"
    MATCH_PAIRS     = "match_pairs"
    SORT_ITEMS      = "sort_items"
    IMAGE_LABEL     = "image_label"


class QuizStrategy(str, Enum):
    EASY_FIRST = "easy_first"
    HARD_FIRST = "hard_first"
    RANDOM     = "random"


QuizDomain = Literal["math_formula", "programming", "language", "memorization", "calculation", "general"]


@dataclass
class Quiz:
    quiz_id: str
    topic_id: str
    domain: QuizDomain
    concept: str
    question: str
    question_type: QuestionType

    # domain 專用欄位（不適用時為 None）
    formula_tokens: list[str] | None = None   # math_formula fill_blank
    symbol_palette: list[str] | None = None   # math_formula short_answer
    code_snippet: str | None = None           # programming
    image_ref: str | None = None              # memorization image_label
    sort_items: list[str] | None = None       # memorization sort_items
    match_pairs: list[list[str]] | None = None  # language match_pairs
    numeric_tolerance: float | None = None    # calculation fill_blank

    options: list[str] | None = None          # MCQ / fill_blank 選項
    hint: str = ""
    correct_answer: str | list | None = None  # 後端用，不回傳前端


@dataclass
class QuizResult:
    quiz_id: str
    score: float                    # 0.0–1.0
    feedback: str
    comprehension_updated: float    # 更新後理解分
    retention_updated: float        # 更新後記憶分
    pending_confirmation: bool
    next_review_due: str | None


# ── 題型選擇矩陣 ─────────────────────────────────────────────────────────────

_EASY_FIRST: dict[QuizDomain, dict[str, QuestionType]] = {
    "math_formula":  {"low": QuestionType.FILL_BLANK,      "mid": QuestionType.MULTIPLE_CHOICE, "high": QuestionType.SHORT_ANSWER},
    "programming":   {"low": QuestionType.FILL_BLANK,      "mid": QuestionType.MULTIPLE_CHOICE, "high": QuestionType.TRUE_FALSE},
    "language":      {"low": QuestionType.FILL_BLANK,      "mid": QuestionType.MULTIPLE_CHOICE, "high": QuestionType.MATCH_PAIRS},
    "memorization":  {"low": QuestionType.TRUE_FALSE,      "mid": QuestionType.SORT_ITEMS,      "high": QuestionType.IMAGE_LABEL},
    "calculation":   {"low": QuestionType.FILL_BLANK,      "mid": QuestionType.MULTIPLE_CHOICE, "high": QuestionType.SHORT_ANSWER},
    "general":       {"low": QuestionType.SHORT_ANSWER,    "mid": QuestionType.MULTIPLE_CHOICE, "high": QuestionType.TRUE_FALSE},
}

_HARD_FIRST: dict[QuizDomain, dict[str, QuestionType]] = {
    "math_formula":  {"low": QuestionType.TRUE_FALSE,   "mid": QuestionType.MULTIPLE_CHOICE, "high": QuestionType.SHORT_ANSWER},
    "programming":   {"low": QuestionType.TRUE_FALSE,   "mid": QuestionType.MULTIPLE_CHOICE, "high": QuestionType.FILL_BLANK},
    "language":      {"low": QuestionType.TRUE_FALSE,   "mid": QuestionType.MULTIPLE_CHOICE, "high": QuestionType.FILL_BLANK},
    "memorization":  {"low": QuestionType.IMAGE_LABEL,  "mid": QuestionType.SORT_ITEMS,      "high": QuestionType.TRUE_FALSE},
    "calculation":   {"low": QuestionType.MULTIPLE_CHOICE, "mid": QuestionType.FILL_BLANK,   "high": QuestionType.SHORT_ANSWER},
    "general":       {"low": QuestionType.TRUE_FALSE,   "mid": QuestionType.MULTIPLE_CHOICE, "high": QuestionType.SHORT_ANSWER},
}


def _mastery_band(score: float) -> str:
    if score < 0.4:
        return "low"
    elif score < 0.7:
        return "mid"
    else:
        return "high"


def _select_question_type(
    domain: QuizDomain,
    score: float,
    strategy: QuizStrategy,
) -> QuestionType:
    import random
    if strategy == QuizStrategy.RANDOM:
        return random.choice([QuestionType.SHORT_ANSWER, QuestionType.MULTIPLE_CHOICE,
                              QuestionType.TRUE_FALSE, QuestionType.FILL_BLANK])
    matrix = _EASY_FIRST if strategy == QuizStrategy.EASY_FIRST else _HARD_FIRST
    band = _mastery_band(score)
    domain_matrix = matrix.get(domain, matrix["general"])
    return domain_matrix.get(band, QuestionType.SHORT_ANSWER)


# ── 公開介面 ──────────────────────────────────────────────────────────────────

async def generate(
    topic_id: str,
    concept_id: str,
    strategy: QuizStrategy = QuizStrategy.EASY_FIRST,
) -> Quiz:
    """生成一道自適應題目"""
    record = await kb.get_mastery(concept_id)
    chunks = await kb.get_chunks_by_topic(topic_id)
    context = "\n\n".join(c.content[:600] for c in chunks[:5])
    if len(context) > 2500:
        context = context[:2500] + "\n...(已截斷)"

    client = GemmaClient()

    # Step 1: Domain 偵測
    domain = await _detect_domain(client, context, record.concept_name)

    # Step 2: 題型選擇
    q_type = _select_question_type(domain, record.comprehension_score, strategy)

    # Step 3: 出題
    quiz = await _generate_quiz(client, record, context, domain, q_type)
    return quiz


async def evaluate(
    quiz: Quiz,
    user_answer: str,
    concept_id: str,
) -> QuizResult:
    """
    評估答案，更新掌握度（comprehension + retention 雙軸）。
    """
    client = GemmaClient()
    score, feedback = await _evaluate_answer(client, quiz, user_answer)

    # 更新理解軸
    from datetime import datetime, timezone
    from backend.engine import knowledge_base as kb

    c_verdict = _score_to_verdict(score)
    c_event = kb.ComprehensionEvent(
        timestamp=datetime.now(timezone.utc),
        question_type=quiz.question_type.value,
        user_answer=user_answer,
        gemma_verdict=c_verdict,
        gemma_reasoning=feedback,
        score_delta=0.0,
        is_delayed_test=False,
    )
    updated_c = await kb.update_comprehension(concept_id, c_event)

    # 更新記憶軸
    r_quality = int(score * 5)
    r_event = kb.RetentionEvent(
        timestamp=datetime.now(timezone.utc),
        question_type=quiz.question_type.value,
        response_quality=r_quality,
        new_interval=1,
        new_easiness=2.5,
    )
    updated_r = await kb.update_retention(concept_id, r_event)

    next_due = updated_r.next_review_due.isoformat() if updated_r.next_review_due else None

    return QuizResult(
        quiz_id=quiz.quiz_id,
        score=score,
        feedback=feedback,
        comprehension_updated=updated_c.comprehension_score,
        retention_updated=updated_r.retention_score,
        pending_confirmation=updated_c.pending_confirmation,
        next_review_due=next_due,
    )


# ── 內部函式 ──────────────────────────────────────────────────────────────────

async def _detect_domain(
    client: GemmaClient,
    context: str,
    concept_name: str,
) -> QuizDomain:
    prompt = (
        f"分析以下學習材料，判斷其科目領域。\n"
        f"概念：「{concept_name}」\n"
        f"材料摘要：\n{context[:1000]}\n\n"
        f"可選領域：math_formula / programming / language / memorization / calculation / general\n"
        f"判斷依據：\n"
        f"  math_formula   — LaTeX、希臘字母、公式佔比高\n"
        f"  programming    — code fence、函式定義、縮排結構\n"
        f"  language       — 長段落、詞彙解釋、語言學\n"
        f"  memorization   — 大量條列、時間軸、圖片密度高\n"
        f"  calculation    — 數值計算、單位換算、公式代入數字\n"
        f"  general        — 不符合以上任一\n\n"
        f"只回傳 JSON：{{\"domain\": \"...\"}}"
    )
    try:
        raw = await client.generate(prompt, mode="edge")
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            d = data.get("domain", "general")
            if d in ("math_formula", "programming", "language", "memorization", "calculation", "general"):
                return d  # type: ignore[return-value]
    except Exception as e:
        logger.warning(f"[quiz_engine] domain 偵測失敗：{e}")
    return "general"


async def _generate_quiz(
    client: GemmaClient,
    record: kb.MasteryRecord,
    context: str,
    domain: QuizDomain,
    q_type: QuestionType,
) -> Quiz:
    q_type_desc = {
        QuestionType.SHORT_ANSWER:    "開放式簡答題（學生需用自己的話回答）",
        QuestionType.MULTIPLE_CHOICE: "四選一選擇題（A/B/C/D）",
        QuestionType.TRUE_FALSE:      "是非題（陳述句，回答「是」或「否」）",
        QuestionType.FILL_BLANK:      "填空題（關鍵詞位置留空用 ___ 表示）",
        QuestionType.MATCH_PAIRS:     "配對題（術語與定義配對，提供至少 4 組）",
        QuestionType.SORT_ITEMS:      "排序題（提供待排序的 4–6 個項目）",
        QuestionType.IMAGE_LABEL:     "圖片標號題（描述圖示內容，提供 3–5 個標注選項）",
    }

    domain_hint = ""
    if domain == "math_formula" and q_type == QuestionType.FILL_BLANK:
        domain_hint = "（需提供 formula_tokens：公式中可點擊填入的元素列表）"
    elif domain == "math_formula" and q_type == QuestionType.SHORT_ANSWER:
        domain_hint = "（需提供 symbol_palette：旁側符號面板，如 α β γ ∑ ∫）"
    elif domain == "programming":
        domain_hint = "（需提供 code_snippet：題目使用的程式碼區塊）"
    elif domain == "calculation" and q_type == QuestionType.FILL_BLANK:
        domain_hint = "（需提供 numeric_tolerance：允許的數值誤差，如 0.01）"

    prompt = (
        f"你是 Domain-Aware 出題系統。\n\n"
        f"概念：「{record.concept_name}」\n"
        f"領域：{domain}\n"
        f"學生理解分數：{record.comprehension_score:.2f}\n"
        f"題型：{q_type.value}（{q_type_desc.get(q_type, '')}）{domain_hint}\n\n"
        f"參考材料：\n{context}\n\n"
        f"請生成嚴格 JSON，包含以下欄位（不需要的欄位設為 null）：\n"
        f"{{\"question\": str, \"options\": list|null, \"formula_tokens\": list|null, "
        f"\"symbol_palette\": list|null, \"code_snippet\": str|null, "
        f"\"sort_items\": list|null, \"match_pairs\": [[str,str]]|null, "
        f"\"numeric_tolerance\": float|null, "
        f"\"correct_answer\": str|list, \"hint\": str}}\n"
        f"確保題目具有真實學習價值，無法靠短期記憶或猜測作答。"
    )

    try:
        raw = await client.generate(prompt, mode="auto")
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return Quiz(
                quiz_id=str(uuid.uuid4()),
                topic_id=record.topic_id,
                domain=domain,
                concept=record.concept_name,
                question=data.get("question", ""),
                question_type=q_type,
                formula_tokens=data.get("formula_tokens"),
                symbol_palette=data.get("symbol_palette"),
                code_snippet=data.get("code_snippet"),
                sort_items=data.get("sort_items"),
                match_pairs=data.get("match_pairs"),
                numeric_tolerance=data.get("numeric_tolerance"),
                options=data.get("options"),
                hint=data.get("hint", ""),
                correct_answer=data.get("correct_answer", ""),
            )
    except Exception as e:
        logger.warning(f"[quiz_engine] 出題失敗：{e}")

    # Fallback
    return Quiz(
        quiz_id=str(uuid.uuid4()),
        topic_id=record.topic_id,
        domain=domain,
        concept=record.concept_name,
        question=f"請解釋「{record.concept_name}」的核心概念。",
        question_type=QuestionType.SHORT_ANSWER,
        correct_answer="",
    )


async def _evaluate_answer(
    client: GemmaClient,
    quiz: Quiz,
    user_answer: str,
) -> tuple[float, str]:
    """評估答案，回傳 (score 0.0–1.0, feedback)"""
    if not user_answer.strip():
        return 0.0, "未作答"

    prompt = (
        f"評估以下學習題目的答案。\n\n"
        f"概念：「{quiz.concept}」\n"
        f"題目：{quiz.question}\n"
        f"題型：{quiz.question_type.value}\n"
        f"正確答案：{json.dumps(quiz.correct_answer, ensure_ascii=False)}\n"
        f"學生答案：{user_answer}\n\n"
        f"給出 0.0–1.0 的分數和一句話回饋（正向鼓勵為主，指出具體不足）。\n"
        f"只回傳 JSON：{{\"score\": float, \"feedback\": str}}"
    )

    try:
        raw = await client.generate(prompt, mode="auto")
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            score = max(0.0, min(1.0, float(data.get("score", 0.5))))
            feedback = data.get("feedback", "")
            return score, feedback
    except Exception as e:
        logger.warning(f"[quiz_engine] 評估失敗：{e}")

    return 0.5, "評估暫時無法回應，已記錄你的答案"


def _score_to_verdict(score: float) -> str:
    if score >= 0.85:
        return "deep"
    elif score >= 0.65:
        return "solid"
    elif score >= 0.35:
        return "partial"
    else:
        return "no_understanding"

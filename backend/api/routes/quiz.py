"""
/v1/topics/{id}/quiz — 自適應測驗路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ── 暫存：將 Quiz 物件（含 correct_answer）存在記憶體供評估時使用 ─────────────
# 正式環境應存入 DB，此為 MVP 實作
_quiz_store: dict[str, object] = {}


# ── Request / Response schemas ────────────────────────────────────────────────

class AnswerRequest(BaseModel):
    user_answer: str


# ── 路由 ──────────────────────────────────────────────────────────────────────

@router.get("/{topic_id}/quiz")
async def generate_quiz(
    topic_id: str,
    concept_id: str,
    strategy: str = "easy_first",
):
    """
    GET /v1/topics/{id}/quiz?concept_id=...&strategy=easy_first|hard_first|random
    生成一道自適應題目，回傳題目資料（不含 correct_answer）。
    """
    from backend.engine.quiz_engine import generate, QuizStrategy

    try:
        strat = QuizStrategy(strategy)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"無效的 strategy：{strategy}")

    try:
        quiz = await generate(topic_id=topic_id, concept_id=concept_id, strategy=strat)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"概念不存在：{concept_id}")

    # 暫存含 correct_answer 的版本
    _quiz_store[quiz.quiz_id] = quiz

    # 回傳不含 correct_answer
    return {
        "quiz_id": quiz.quiz_id,
        "topic_id": quiz.topic_id,
        "domain": quiz.domain,
        "concept": quiz.concept,
        "question": quiz.question,
        "question_type": quiz.question_type.value,
        "options": quiz.options,
        "formula_tokens": quiz.formula_tokens,
        "symbol_palette": quiz.symbol_palette,
        "code_snippet": quiz.code_snippet,
        "sort_items": quiz.sort_items,
        "match_pairs": quiz.match_pairs,
        "numeric_tolerance": quiz.numeric_tolerance,
        "hint": quiz.hint,
    }


@router.post("/{topic_id}/quiz/answer")
async def submit_answer(
    topic_id: str,
    quiz_id: str,
    concept_id: str,
    body: AnswerRequest,
):
    """
    POST /v1/topics/{id}/quiz/answer?quiz_id=...&concept_id=...
    提交答案，更新雙軸掌握度，回傳評估結果。
    """
    from backend.engine.quiz_engine import evaluate

    quiz = _quiz_store.get(quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail=f"Quiz 不存在或已過期：{quiz_id}")

    try:
        result = await evaluate(quiz=quiz, user_answer=body.user_answer, concept_id=concept_id)  # type: ignore[arg-type]
    except KeyError:
        raise HTTPException(status_code=404, detail=f"概念不存在：{concept_id}")
    finally:
        # 用完後清除（correct_answer 不應長期暫存）
        _quiz_store.pop(quiz_id, None)

    return {
        "quiz_id": result.quiz_id,
        "score": result.score,
        "feedback": result.feedback,
        "comprehension_updated": result.comprehension_updated,
        "retention_updated": result.retention_updated,
        "pending_confirmation": result.pending_confirmation,
        "pending_message": "✳️ 初步確認，明天再來驗證！" if result.pending_confirmation else None,
        "next_review_due": result.next_review_due,
    }

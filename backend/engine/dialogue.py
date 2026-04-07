"""
蘇格拉底式追問對話模組
RUNTIME: auto
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# RUNTIME: auto

SOCRATIC_SYSTEM_PROMPT = """你是一個蘇格拉底式學習助教，目標是幫助學生真正理解一個概念，而不是直接給答案。

規則：
1. 不要直接解釋答案，用問題引導學生自己想
2. 如果學生的回答不完整，繼續追問
3. 如果學生說「不知道」，給一個提示性的小問題
4. 用學生自己的語言和例子，不要用技術術語
5. 每次只問一個問題
6. 當你判斷學生已經真正理解時，給予正向回饋並結束對話

當前討論的盲點概念：{concept}
學生已知的相關背景：{background}
"""

DEPTH_ASSESSMENT_PROMPT = """根據以下學生的回答，評估他對「{concept}」的理解深度。

學生的回答：
{answer}

請回傳 0.0 到 1.0 之間的數字，代表理解深度（只回傳數字，不要其他文字）：
- 0.0–0.3：完全不理解
- 0.3–0.6：部分理解，有明顯缺口
- 0.6–0.8：大致理解，有些細節不清楚
- 0.8–1.0：充分理解，能用自己的話解釋
"""


@dataclass
class DialogueTurn:
    role: str       # "assistant" | "user"
    content: str


@dataclass
class DialogueSession:
    session_id: str
    blind_spot_id: str
    concept: str
    turns: list[DialogueTurn] = field(default_factory=list)
    final_confidence: float | None = None
    is_completed: bool = False


async def start_dialogue(concept: str, background: str = "", session_id: str = "") -> str:
    """開始蘇格拉底對話，回傳第一個問題"""
    from backend.engine.gemma_client import GemmaClient

    client = GemmaClient()
    system = SOCRATIC_SYSTEM_PROMPT.format(concept=concept, background=background)
    prompt = f"{system}\n\n請用一個問題開始對話，引導學生思考「{concept}」。"
    return await client.generate(prompt=prompt, mode="auto")


async def continue_dialogue(
    concept: str,
    history: list[DialogueTurn],
    user_answer: str,
) -> tuple[str, float]:
    """
    繼續對話。
    回傳 (下一個問題或結束語, 理解深度 0.0–1.0)
    """
    from backend.engine.gemma_client import GemmaClient

    client = GemmaClient()

    # 評估回答深度
    depth_prompt = DEPTH_ASSESSMENT_PROMPT.format(concept=concept, answer=user_answer)
    depth_raw = await client.generate(prompt=depth_prompt, mode="edge")
    try:
        depth = float(depth_raw.strip().split()[0])
        depth = max(0.0, min(1.0, depth))
    except (ValueError, IndexError):
        depth = 0.5

    # 如果已充分理解，結束對話
    if depth >= 0.8:
        closing = f"很棒！你已經能清楚解釋「{concept}」了。我們把它標記為理解完成 ✓"
        return closing, depth

    # 繼續追問
    history_text = "\n".join(
        f"{'學生' if t.role == 'user' else 'AI'}: {t.content}" for t in history[-6:]
    )
    system = SOCRATIC_SYSTEM_PROMPT.format(concept=concept, background="")
    prompt = (
        f"{system}\n\n"
        f"對話紀錄：\n{history_text}\n"
        f"學生最新回答：{user_answer}\n\n"
        f"請根據學生的回答，繼續用一個問題引導他更深入理解。"
    )
    next_question = await client.generate(prompt=prompt, mode="auto")
    return next_question, depth

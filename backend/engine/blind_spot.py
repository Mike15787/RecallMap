"""
知識盲點偵測模組
RUNTIME: auto（短 prompt 走 edge，複雜分析走 cloud）
"""
import json
import logging
from dataclasses import dataclass, field

from backend.ingest.base import ChunkList, DocumentChunk

logger = logging.getLogger(__name__)

# RUNTIME: auto


@dataclass
class BlindSpot:
    concept: str                        # 盲點概念名稱
    confidence: float                   # 0.0–1.0，AI 判斷這是盲點的信心度
    evidence: list[str] = field(default_factory=list)  # 支撐判斷的原文片段
    repeat_count: int = 0               # 在對話紀錄中反覆出現的次數
    blind_spot_id: str = ""             # 唯一 ID（由 session 層產生）


BLIND_SPOT_PROMPT = """你是一個學習分析 AI，任務是從學生的學習材料中找出知識盲點。

以下是學生的學習內容（筆記、對話紀錄等）：
{content}

請分析並找出 3–7 個知識盲點，判斷標準：
1. 概念被反覆提問但沒有深入追問
2. 筆記記錄了但解釋模糊或不完整
3. 問過 AI 但回覆只被接受、沒有再追問確認

請以 JSON 格式回覆，格式如下（只回覆 JSON，不要加任何說明）：
[
  {{
    "concept": "概念名稱",
    "confidence": 0.85,
    "evidence": ["原文片段1", "原文片段2"],
    "repeat_count": 3
  }}
]
"""


async def detect(chunks: ChunkList) -> list[BlindSpot]:
    """
    從 DocumentChunk 列表中偵測知識盲點。
    對話紀錄和筆記會一起分析，交叉比對。
    """
    from backend.engine.gemma_client import GemmaClient

    if not chunks:
        return []

    content = _prepare_content(chunks)
    prompt = BLIND_SPOT_PROMPT.format(content=content[:6000])  # 避免超出 context

    client = GemmaClient()
    try:
        raw = await client.generate(prompt=prompt, mode="auto")
        return _parse_response(raw)
    except Exception as e:
        logger.error(f"盲點偵測失敗：{e}")
        return []


def _prepare_content(chunks: ChunkList) -> str:
    """將 chunks 整理成可讀文字，對話紀錄和筆記分開標示"""
    note_parts: list[str] = []
    conv_parts: list[str] = []

    for chunk in chunks:
        if chunk.is_conversation:
            conv_parts.append(chunk.content)
        else:
            note_parts.append(chunk.content)

    sections = []
    if note_parts:
        sections.append("【筆記內容】\n" + "\n---\n".join(note_parts))
    if conv_parts:
        sections.append("【AI 對話紀錄】\n" + "\n---\n".join(conv_parts))

    return "\n\n".join(sections)


def _parse_response(raw: str) -> list[BlindSpot]:
    """解析模型回傳的 JSON"""
    # 嘗試從回應中提取 JSON 陣列
    raw = raw.strip()
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        logger.warning("模型回應中找不到 JSON 陣列")
        return []

    try:
        items = json.loads(raw[start:end])
        spots: list[BlindSpot] = []
        for item in items:
            spots.append(
                BlindSpot(
                    concept=item.get("concept", "未知概念"),
                    confidence=float(item.get("confidence", 0.5)),
                    evidence=item.get("evidence", []),
                    repeat_count=int(item.get("repeat_count", 0)),
                )
            )
        return spots
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"解析盲點 JSON 失敗：{e}\n原始回應：{raw[:200]}")
        return []

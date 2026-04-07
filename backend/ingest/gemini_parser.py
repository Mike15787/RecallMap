"""
Gemini Takeout 匯出解析器
RUNTIME: edge（純邏輯，不需要模型）

匯出方式：Google Takeout → 選 Gemini Apps Activity → 下載 → MyActivity.json
格式參考：Takeout/Gemini Apps Activity/MyActivity.json
"""
import json
from pathlib import Path

from .base import ChunkList, DocumentChunk, SourceType
from .chatgpt_parser import EXCLUSION_SIGNALS, LEARNING_SIGNALS


async def process(source: str | Path | dict) -> ChunkList:
    """
    單一公開入口。
    接受 MyActivity.json 路徑或已解析的 dict/list。
    """
    if isinstance(source, (dict, list)):
        data = source
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"找不到檔案：{path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

    # Gemini Takeout 格式：list of activity objects
    activities = data if isinstance(data, list) else data.get("activity", [])
    if not activities:
        raise ValueError("無法識別 Gemini Takeout 格式，請確認是 MyActivity.json")

    chunks: ChunkList = []
    for i, activity in enumerate(activities):
        chunk = _parse_activity(activity, i)
        if chunk:
            chunks.append(chunk)

    return chunks


def _parse_activity(activity: dict, index: int) -> DocumentChunk | None:
    """解析單一 Gemini 活動記錄"""
    # Gemini Takeout 結構：title, time, details[].activityControls / products
    title = activity.get("title", "")
    time_str = activity.get("time", "")

    # 從 subtitles 或 details 取出提問內容
    subtitles = activity.get("subtitles", [])
    query_text = ""
    for sub in subtitles:
        name = sub.get("name", "")
        if name:
            query_text += name + " "
    query_text = query_text.strip() or title

    if not query_text:
        return None

    if not _is_learning_query(query_text):
        return None

    return DocumentChunk(
        content=f"Q: {query_text}",
        source_type=SourceType.GEMINI,
        source_id=f"gemini::activity{index}",
        is_conversation=True,
        metadata={
            "title": title,
            "timestamp": time_str,
            "index": index,
        },
    )


def _is_learning_query(text: str) -> bool:
    text_lower = text.lower()
    has_learning = any(signal in text_lower for signal in LEARNING_SIGNALS)
    has_exclusion = any(signal in text_lower for signal in EXCLUSION_SIGNALS)
    return has_learning and not has_exclusion

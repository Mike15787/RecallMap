"""
ChatGPT 匯出 JSON 解析器
RUNTIME: edge（純邏輯，不需要模型）

匯出方式：ChatGPT 設定 → 資料控制 → 匯出資料 → conversations.json
"""
import json
import re
from pathlib import Path

from .base import ChunkList, DocumentChunk, SourceType

# 學習對話信號（符合其中一項 → 視為學習對話）
LEARNING_SIGNALS = [
    "為什麼", "怎麼", "什麼是", "如何", "解釋", "說明", "幫我理解",
    "why", "how", "what is", "explain", "difference between",
    "what does", "can you explain", "tell me about",
]

# 非學習對話排除信號（符合即排除）
EXCLUSION_SIGNALS = [
    "幫我寫", "幫我做", "生成", "翻譯這段", "幫我翻",
    "write me", "generate", "create a", "translate this",
    "write a", "draft a", "make me",
]


async def process(source: str | Path | dict | list) -> ChunkList:
    """
    單一公開入口。
    接受 conversations.json 路徑、已解析的 dict 或 list。
    """
    if isinstance(source, list):
        conversations = source
    elif isinstance(source, dict):
        if "conversations" in source:
            conversations = source["conversations"]
        else:
            raise ValueError("無法識別 ChatGPT 匯出格式，請確認是 conversations.json")
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"找不到檔案：{path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            conversations = data
        elif isinstance(data, dict) and "conversations" in data:
            conversations = data["conversations"]
        else:
            raise ValueError("無法識別 ChatGPT 匯出格式，請確認是 conversations.json")

    chunks: ChunkList = []
    for conv in conversations:
        conv_chunks = _parse_conversation(conv)
        chunks.extend(conv_chunks)

    return chunks


def _parse_conversation(conv: dict) -> ChunkList:
    """解析單一對話，過濾非學習對話，每輪問答合為一個 chunk"""
    title = conv.get("title", "未命名對話")
    conv_id = conv.get("id", "unknown")
    mapping = conv.get("mapping", {})

    # 依時間排序取出所有訊息
    messages = _extract_messages(mapping)
    if not messages:
        return []

    # 過濾：只保留包含學習信號的對話段落
    learning_turns: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        text = msg.get("text", "")
        if role == "user" and _is_learning_query(text):
            learning_turns.append(msg)
        elif role == "assistant" and learning_turns:
            # 配對：把 AI 回覆附加到最後一個學習問題上
            learning_turns[-1]["answer"] = text

    chunks: ChunkList = []
    for i, turn in enumerate(learning_turns):
        question = turn.get("text", "")
        answer = turn.get("answer", "")
        if not question:
            continue

        content = f"Q: {question}"
        if answer:
            content += f"\nA: {answer}"

        chunks.append(
            DocumentChunk(
                content=content,
                source_type=SourceType.CHATGPT,
                source_id=f"chatgpt::{conv_id}::turn{i}",
                is_conversation=True,
                metadata={
                    "conversation_title": title,
                    "conversation_id": conv_id,
                    "turn_index": i,
                    "timestamp": turn.get("create_time"),
                },
            )
        )
    return chunks


def _extract_messages(mapping: dict) -> list[dict]:
    """從 mapping 結構中按順序提取訊息"""
    messages = []
    for node in mapping.values():
        msg = node.get("message")
        if not msg:
            continue
        role = msg.get("author", {}).get("role")
        if role not in ("user", "assistant"):
            continue
        # 取出文字內容
        parts = msg.get("content", {}).get("parts", [])
        text = " ".join(str(p) for p in parts if isinstance(p, str)).strip()
        if not text:
            continue
        messages.append({
            "role": role,
            "text": text,
            "create_time": msg.get("create_time", 0),
        })
    messages.sort(key=lambda m: m["create_time"] or 0)
    return messages


def _is_learning_query(text: str) -> bool:
    """判斷是否為學習型提問"""
    text_lower = text.lower()
    has_learning = any(signal in text_lower for signal in LEARNING_SIGNALS)
    has_exclusion = any(signal in text_lower for signal in EXCLUSION_SIGNALS)
    return has_learning and not has_exclusion


def count_repeated_topics(chunks: ChunkList) -> dict[str, int]:
    """
    統計各對話中反覆出現的主題（用於盲點偵測前處理）。
    回傳 {主題關鍵字: 出現次數}
    """
    from collections import Counter
    # 簡單版：提取問句中的名詞片語（3+ 字中文詞組 或 英文片語）
    topic_counter: Counter = Counter()
    for chunk in chunks:
        if not chunk.is_conversation:
            continue
        # 取第一行（問題部分）
        question_line = chunk.content.split("\n")[0].replace("Q: ", "")
        # 中文詞組（3–8 字）
        for match in re.finditer(r"[\u4e00-\u9fff]{3,8}", question_line):
            topic_counter[match.group()] += 1
        # 英文片語（2–4 個單字）
        words = re.findall(r"[a-zA-Z]+", question_line.lower())
        for i in range(len(words) - 1):
            phrase = " ".join(words[i : i + 2])
            topic_counter[phrase] += 1
    # 只回傳出現 2 次以上的
    return {k: v for k, v in topic_counter.items() if v >= 2}

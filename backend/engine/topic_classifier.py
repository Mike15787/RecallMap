"""
主題分類器 — 將 chunks 動態歸類到知識庫主題
RUNTIME: auto（Gemma edge 語意比對；結果合併到 knowledge_base）

輸入：ChunkList
輸出：list[TopicCluster]

流程：
  1. 呼叫 Gemma 從 chunks 提取候選主題名稱
  2. 對每個候選主題呼叫 knowledge_base.find_similar_topic() 語意比對
  3. 有相似主題 → is_new=False，合併；無 → is_new=True，建立新主題
  4. 呼叫 add_chunks_to_topic 把 chunks 存入知識庫
"""
import json
import logging
import re
import uuid
from dataclasses import dataclass, field

from backend.ingest.base import ChunkList
from backend.engine import knowledge_base as kb
from backend.engine.gemma_client import GemmaClient

logger = logging.getLogger(__name__)

# ── 資料類別 ──────────────────────────────────────────────────────────────────

@dataclass
class TopicCluster:
    topic_id: str
    topic_name: str
    description: str
    chunk_ids: list[str] = field(default_factory=list)
    is_new: bool = True          # True → 知識庫新建；False → 合併入既有


# ── 公開介面 ──────────────────────────────────────────────────────────────────

async def classify(chunks: ChunkList) -> list[TopicCluster]:
    """
    將 chunks 分類到知識庫主題並持久化。
    回傳每個主題的 TopicCluster（含 topic_id）。
    """
    if not chunks:
        return []

    client = GemmaClient()

    # 1. 提取候選主題
    candidates = await _extract_topics(client, chunks)
    if not candidates:
        logger.warning("[topic_classifier] Gemma 未回傳任何主題，使用 fallback")
        candidates = [{"name": "學習材料", "description": "上傳的學習內容"}]

    # 2. 對每個候選主題找相似 / 建立新主題
    clusters: list[TopicCluster] = []
    for c in candidates:
        name = c.get("name", "未命名主題")
        desc = c.get("description", "")
        chunk_indices: list[int] = c.get("chunk_indices", list(range(len(chunks))))

        existing = await kb.find_similar_topic(name)
        if existing:
            topic_id = existing.topic_id
            is_new = False
        else:
            topic = await kb.add_topic(name, desc)
            topic_id = topic.topic_id
            is_new = True

        # 3. 把對應 chunks 寫入知識庫
        selected = [chunks[i] for i in chunk_indices if 0 <= i < len(chunks)]
        if selected:
            await kb.add_chunks_to_topic(topic_id, selected)

        # 為每個 chunk 產生簡單的 chunk_id（以 source_id + index 為依據）
        chunk_ids = [f"{topic_id}-chunk-{i}" for i in chunk_indices]

        clusters.append(
            TopicCluster(
                topic_id=topic_id,
                topic_name=name,
                description=desc,
                chunk_ids=chunk_ids,
                is_new=is_new,
            )
        )

    return clusters


# ── 內部函式 ──────────────────────────────────────────────────────────────────

async def _extract_topics(client: GemmaClient, chunks: ChunkList) -> list[dict]:
    """
    呼叫 Gemma 從 chunks 提取主題名稱與描述。
    回傳 list of {"name": str, "description": str, "chunk_indices": list[int]}
    """
    # 截取前 3000 字做摘要（避免 prompt 過長）
    combined = "\n\n---\n\n".join(
        f"[{i}] {c.content[:600]}" for i, c in enumerate(chunks[:10])
    )
    if len(combined) > 3000:
        combined = combined[:3000] + "\n...(已截斷)"

    prompt = (
        "你是學習知識庫管理員。請分析以下學習材料，辨識其中包含的主要學習主題。\n\n"
        f"材料（最多 10 個片段）：\n{combined}\n\n"
        "請回傳 JSON 陣列，每個元素包含：\n"
        "  name: 主題名稱（簡短，2–10 字，如「Python 遞迴」、「線性代數 - 行列式」）\n"
        "  description: 一句話描述（不超過 30 字）\n"
        "  chunk_indices: 屬於此主題的片段編號（0-based 整數陣列）\n\n"
        "限制：最多回傳 5 個主題。只回傳 JSON，不要其他說明。\n"
        "格式：[{\"name\": \"...\", \"description\": \"...\", \"chunk_indices\": [0, 1]}]"
    )

    try:
        raw = await client.generate(prompt, mode="auto")
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        logger.warning(f"[topic_classifier] 主題提取失敗：{e}")

    return []

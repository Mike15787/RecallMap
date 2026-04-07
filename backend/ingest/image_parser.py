"""
圖片輸入模組 — 手寫筆記、iPad 匯出
RUNTIME: edge（Gemma 4 E4B 多模態，本地處理）
"""
from pathlib import Path

from .base import ChunkList, DocumentChunk, SourceType

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


async def process(source: str | Path) -> ChunkList:
    """
    單一公開入口。
    將圖片送入 Gemma 4 E4B 進行多模態辨識，回傳萃取的文字內容。
    """
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"找不到圖片：{path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支援的圖片格式：{path.suffix}")

    image_bytes = path.read_bytes()
    text = await _recognize_handwriting(image_bytes, path.name)

    return [
        DocumentChunk(
            content=text,
            source_type=SourceType.IMAGE,
            source_id=f"img::{path.stem}",
            metadata={"filename": path.name, "size_bytes": len(image_bytes)},
        )
    ]


async def process_bytes(image_bytes: bytes, filename: str) -> ChunkList:
    """從記憶體中的圖片位元組處理（適用於 API 上傳）"""
    if not filename:
        raise ValueError("filename 不得為空")
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支援的圖片格式：{ext}")

    text = await _recognize_handwriting(image_bytes, filename)
    return [
        DocumentChunk(
            content=text,
            source_type=SourceType.IMAGE,
            source_id=f"img::{Path(filename).stem}",
            metadata={"filename": filename, "size_bytes": len(image_bytes)},
        )
    ]


async def _recognize_handwriting(image_bytes: bytes, filename: str) -> str:
    """呼叫 GemmaClient 進行圖片文字辨識"""
    # 延遲 import 避免循環依賴
    from backend.engine.gemma_client import GemmaClient

    client = GemmaClient()
    prompt = (
        "請仔細辨識這張圖片中的所有文字內容（包含手寫文字）。"
        "保留原始結構（標題、條列、段落），以純文字輸出，不要加任何說明。"
        "若有數學公式，用文字描述。若辨識不確定，標記 [?]。"
    )
    text = await client.generate(prompt=prompt, images=[image_bytes], mode="edge")
    if not text.strip():
        raise ValueError(f"無法從圖片中辨識出文字：{filename}")
    return text.strip()

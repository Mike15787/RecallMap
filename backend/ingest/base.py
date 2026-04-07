from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(Enum):
    PDF     = "pdf"
    PPT     = "ppt"
    WORD    = "word"
    IMAGE   = "image"
    NOTION  = "notion"
    CHATGPT = "chatgpt"
    GEMINI  = "gemini"


@dataclass
class DocumentChunk:
    content: str                    # 純文字內容（必填）
    source_type: SourceType         # 來源類型（必填）
    source_id: str                  # 來源唯一識別碼（必填）
    metadata: dict[str, Any] = field(default_factory=dict)
    is_conversation: bool = False   # 是否為對話紀錄（影響盲點偵測邏輯）
    language: str = "zh-TW"        # 內容語言

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("DocumentChunk.content 不得為空")
        if not self.source_id.strip():
            raise ValueError("DocumentChunk.source_id 不得為空")


ChunkList = list[DocumentChunk]

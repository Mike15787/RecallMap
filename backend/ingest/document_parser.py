"""
PDF / PPTX / DOCX 文字萃取模組（markitdown）
RUNTIME: edge（純 CPU，本地執行，不呼叫任何 AI API）

使用 Microsoft markitdown 統一處理三種文件格式，
轉出 Markdown 後包裝成 DocumentChunk。
掃描版 PDF / 加密文件會拋出明確使用者友善訊息。
圖片辨識請改用 image_parser.py（走 Gemma 多模態）。
"""
from pathlib import Path

from markitdown import MarkItDown

from .base import ChunkList, DocumentChunk, SourceType

# 單例：MarkItDown 初始化有成本，模組載入時建立一次
_md = MarkItDown(enable_plugins=False)

# 支援的副檔名 → SourceType
_EXT_TO_SOURCE: dict[str, SourceType] = {
    ".pdf":  SourceType.PDF,
    ".pptx": SourceType.PPT,
    ".ppt":  SourceType.PPT,
    ".docx": SourceType.WORD,
    ".doc":  SourceType.WORD,
}

# 掃描版 PDF 偵測門檻：萃取文字少於此值視為無文字層
_MIN_CHAR_COUNT = 100


async def process(source: str | Path) -> ChunkList:
    """
    將 PDF / PPTX / DOCX 轉換為 DocumentChunk 列表。
    不呼叫任何 AI，純文字萃取。

    Args:
        source: 檔案路徑

    Returns:
        list[DocumentChunk]，通常只有一個元素（整份文件為一個 chunk）

    Raises:
        ValueError: 不支援的格式、密碼保護、掃描版 PDF 或 markitdown 無法解析
    """
    path = Path(source)
    ext = path.suffix.lower()

    if ext not in _EXT_TO_SOURCE:
        raise ValueError(f"document_parser 不支援此副檔名：{ext}")

    source_type = _EXT_TO_SOURCE[ext]

    try:
        result = _md.convert(str(path))
    except Exception as e:
        err_lower = str(e).lower()
        if "password" in err_lower or "encrypt" in err_lower:
            raise ValueError(
                f"這份文件有密碼保護，請先移除密碼再上傳：{path.name}"
            ) from e
        raise ValueError(f"無法解析檔案 {path.name}：{e}") from e

    markdown_text: str = result.text_content or ""

    if len(markdown_text.strip()) < _MIN_CHAR_COUNT:
        raise ValueError(
            f"從 {path.name} 萃取的文字過少（可能是掃描版 PDF 或空白文件）。"
            "請改用「拍照上傳」功能，走圖片辨識路徑。"
        )

    metadata: dict = {
        "filename": path.name,
        "extension": ext,
        "char_count": len(markdown_text),
    }

    # PPT 含嵌入圖片提示（engine 層可據此建議使用者補充說明）
    if source_type == SourceType.PPT:
        metadata["has_image_content"] = (
            "![" in markdown_text or "<img" in markdown_text.lower()
        )

    return [
        DocumentChunk(
            content=markdown_text,
            source_type=source_type,
            source_id=str(path.resolve()),
            metadata=metadata,
            is_conversation=False,
        )
    ]

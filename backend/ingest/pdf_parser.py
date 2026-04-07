"""
PDF / PPT / Word 文字萃取模組
RUNTIME: edge（不需要模型，純文字萃取）
"""
from pathlib import Path

import fitz  # PyMuPDF
from docx import Document
from pptx import Presentation

from .base import ChunkList, DocumentChunk, SourceType


async def process(source: str | Path) -> ChunkList:
    """
    單一公開入口。
    根據副檔名自動選擇解析策略，回傳 DocumentChunk 列表（每頁/每章節一個 chunk）。
    """
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"找不到檔案：{path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    elif suffix in (".ppt", ".pptx"):
        return _parse_pptx(path)
    elif suffix in (".doc", ".docx"):
        return _parse_docx(path)
    else:
        raise ValueError(f"不支援的格式：{suffix}，請使用 PDF / PPT / PPTX / DOC / DOCX")


def _parse_pdf(path: Path) -> ChunkList:
    chunks: ChunkList = []
    with fitz.open(path) as doc:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if not text:
                continue
            chunks.append(
                DocumentChunk(
                    content=text,
                    source_type=SourceType.PDF,
                    source_id=f"{path.stem}::p{page_num}",
                    metadata={"filename": path.name, "page": page_num, "total_pages": len(doc)},
                )
            )
    return chunks


def _parse_pptx(path: Path) -> ChunkList:
    chunks: ChunkList = []
    prs = Presentation(path)
    for slide_num, slide in enumerate(prs.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = para.text.strip()
                    if line:
                        texts.append(line)
        if not texts:
            continue
        chunks.append(
            DocumentChunk(
                content="\n".join(texts),
                source_type=SourceType.PPT,
                source_id=f"{path.stem}::slide{slide_num}",
                metadata={"filename": path.name, "slide": slide_num},
            )
        )
    return chunks


def _parse_docx(path: Path) -> ChunkList:
    doc = Document(path)
    # 每個 heading 切一個 chunk；沒有 heading 就整份為一個 chunk
    chunks: ChunkList = []
    current_heading = "文件開頭"
    current_lines: list[str] = []

    def _flush(heading: str, lines: list[str], section_num: int) -> None:
        text = "\n".join(lines).strip()
        if text:
            chunks.append(
                DocumentChunk(
                    content=text,
                    source_type=SourceType.WORD,
                    source_id=f"{path.stem}::s{section_num}",
                    metadata={"filename": path.name, "section": heading},
                )
            )

    section_num = 1
    for para in doc.paragraphs:
        if para.style.name.startswith("Heading"):
            _flush(current_heading, current_lines, section_num)
            section_num += 1
            current_heading = para.text.strip() or current_heading
            current_lines = []
        else:
            if para.text.strip():
                current_lines.append(para.text.strip())

    _flush(current_heading, current_lines, section_num)
    return chunks

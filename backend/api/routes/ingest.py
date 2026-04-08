"""
POST /v1/sessions/{id}/ingest — 上傳學習材料
POST /v1/sessions/{id}/ingest/notion — 從 Notion page 匯入
"""
import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.api.store import session_store

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp"}


@router.post("/{session_id}/ingest")
async def ingest_file(
    session_id: str,
    file: UploadFile = File(...),
    source_hint: str | None = Form(None),   # "chatgpt" | "gemini" | "notion" | None（自動偵測）
):
    sess = await session_store.get_or_404(session_id)

    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()
    content = await file.read()

    try:
        chunks = await _dispatch(content, filename, ext, source_hint)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    sess["chunks"].extend(chunks)
    await session_store.save(sess)

    return {
        "status": "ok",
        "filename": filename,
        "chunks_added": len(chunks),
        "total_chunks": len(sess["chunks"]),
    }


@router.post("/{session_id}/ingest/notion")
async def ingest_notion_page(session_id: str, page_id: str = Form(...)):
    """直接從 Notion page ID 匯入"""
    sess = await session_store.get_or_404(session_id)

    from backend.ingest import notion_parser
    chunks = await notion_parser.process(page_id)
    sess["chunks"].extend(chunks)
    await session_store.save(sess)

    return {"status": "ok", "page_id": page_id, "chunks_added": len(chunks)}


async def _dispatch(content: bytes, filename: str, ext: str, source_hint: str | None):
    """根據檔案類型分派到對應 parser"""
    import tempfile
    import os

    # JSON 檔案 → ChatGPT 或 Gemini export
    if ext == ".json" or source_hint in ("chatgpt", "gemini"):
        data = json.loads(content.decode("utf-8"))
        if source_hint == "gemini":
            from backend.ingest import gemini_parser
            return await gemini_parser.process(data)
        else:
            from backend.ingest import chatgpt_parser
            return await chatgpt_parser.process(data)

    # 圖片 → 多模態辨識
    if ext in (".jpg", ".jpeg", ".png", ".webp"):
        from backend.ingest import image_parser
        return await image_parser.process_bytes(content, filename)

    # 文件 → PDF / PPT / Word（需要寫到暫存檔）
    if ext in (".pdf", ".ppt", ".pptx", ".doc", ".docx"):
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            from backend.ingest import pdf_parser
            return await pdf_parser.process(tmp_path)
        finally:
            os.unlink(tmp_path)

    raise ValueError(f"不支援的檔案類型：{ext}")

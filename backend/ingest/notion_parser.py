"""
Notion 筆記串接模組
RUNTIME: edge（API 呼叫，不需要模型）
"""
from .base import ChunkList, DocumentChunk, SourceType


async def process(source: str | dict) -> ChunkList:
    """
    單一公開入口。
    source 可以是 Notion page ID（字串）或已取得的 page dict。
    """
    if isinstance(source, dict):
        page_id = source.get("id", "")
        page_title = _extract_title(source)
        blocks = source.get("blocks", [])
        return _blocks_to_chunks(blocks, page_id, page_title)
    else:
        page_id = source.strip()
        return await _fetch_and_parse(page_id)


async def _fetch_and_parse(page_id: str) -> ChunkList:
    from backend.integrations.notion_api import get_page_title, get_all_blocks

    title = await get_page_title(page_id)
    blocks = await get_all_blocks(page_id)
    return _blocks_to_chunks(blocks, page_id, title)


def _blocks_to_chunks(blocks: list[dict], page_id: str, page_title: str) -> ChunkList:
    """將 Notion block 列表轉換為 DocumentChunk，依 heading 切分章節"""
    chunks: ChunkList = []
    current_section = page_title or "筆記"
    current_lines: list[str] = []
    section_num = 0

    def _flush() -> None:
        nonlocal section_num
        text = "\n".join(current_lines).strip()
        if text:
            chunks.append(
                DocumentChunk(
                    content=text,
                    source_type=SourceType.NOTION,
                    source_id=f"notion::{page_id}::s{section_num}",
                    metadata={"page_id": page_id, "page_title": page_title, "section": current_section},
                )
            )
            section_num += 1

    for block in blocks:
        block_type = block.get("type", "")
        text = _extract_block_text(block)
        if not text:
            continue

        if block_type in ("heading_1", "heading_2", "heading_3"):
            _flush()
            current_section = text
            current_lines = []
        else:
            current_lines.append(text)

    _flush()
    return chunks


def _extract_block_text(block: dict) -> str:
    """從各種 block 類型萃取純文字"""
    block_type = block.get("type", "")
    rich_texts = block.get(block_type, {}).get("rich_text", [])
    return "".join(rt.get("plain_text", "") for rt in rich_texts).strip()


def _extract_title(page: dict) -> str:
    props = page.get("properties", {})
    for key in ("title", "Name", "名稱"):
        if key in props:
            rich_texts = props[key].get("title", [])
            return "".join(rt.get("plain_text", "") for rt in rich_texts).strip()
    return "Notion 筆記"

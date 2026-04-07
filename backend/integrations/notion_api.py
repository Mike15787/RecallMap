"""
Notion API 串接模組
"""
import os

from notion_client import AsyncClient

# 授權 token 必須從環境變數讀取，禁止寫死
def _get_client() -> AsyncClient:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise EnvironmentError("缺少環境變數 NOTION_TOKEN")
    return AsyncClient(auth=token)


async def get_page_title(page_id: str) -> str:
    client = _get_client()
    page = await client.pages.retrieve(page_id=page_id)
    props = page.get("properties", {})
    for key in ("title", "Name", "名稱"):
        if key in props:
            rich_texts = props[key].get("title", [])
            return "".join(rt.get("plain_text", "") for rt in rich_texts).strip()
    return "Notion 筆記"


async def get_all_blocks(page_id: str) -> list[dict]:
    """讀取頁面所有 block，處理分頁"""
    client = _get_client()
    blocks: list[dict] = []
    cursor = None
    while True:
        kwargs = {"block_id": page_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = await client.blocks.children.list(**kwargs)
        blocks.extend(resp["results"])
        if not resp["has_more"]:
            break
        cursor = resp["next_cursor"]
    return blocks


async def search_pages(query: str, page_size: int = 10) -> list[dict]:
    """搜尋 Notion workspace"""
    client = _get_client()
    resp = await client.search(query=query, filter={"property": "object", "value": "page"}, page_size=page_size)
    return resp.get("results", [])

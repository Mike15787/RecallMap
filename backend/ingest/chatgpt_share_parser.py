"""
ChatGPT 分享連結爬取模組
RUNTIME: edge（本機執行，對話內容不上傳第三方）

使用 Playwright 無頭瀏覽器爬取 ChatGPT 分享頁面。
頁面為 Next.js SSR，對話資料存在 __NEXT_DATA__ script tag 的 JSON 中。
直接解析 JSON 比 DOM 解析更穩定，不易因 UI 改版失效。

安裝需求：
  pip install playwright
  playwright install chromium

⚠️  全帳號歷史紀錄爬取絕對禁止（技術、法律、合規三重風險）。
    僅支援使用者主動分享的單篇對話連結。
"""
import json
import logging
import re
from pathlib import Path

from .base import ChunkList, DocumentChunk, SourceType

logger = logging.getLogger(__name__)

# ChatGPT 分享連結格式
_CHATGPT_SHARE_PATTERN = re.compile(
    r'^https://chatgpt\.com/share/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
)

# 學習對話過濾條件（與 chatgpt_parser.py 相同規則）
_LEARNING_SIGNALS = [
    "為什麼", "怎麼", "什麼是", "如何", "解釋", "原理", "概念",
    "why", "how", "what is", "explain", "difference between", "define",
    "understand", "理解", "學習",
]

_EXCLUSION_SIGNALS = [
    "幫我寫", "幫我做", "生成", "翻譯這段", "幫我翻",
    "write me", "generate", "create a", "translate",
    "寫一首", "幫忙寫",
]


def validate_share_url(url: str) -> bool:
    """檢驗是否為合法的 ChatGPT 分享連結"""
    return bool(_CHATGPT_SHARE_PATTERN.match(url.strip()))


async def process(share_url: str) -> ChunkList:
    """
    從 ChatGPT 分享連結爬取對話內容並轉換成 DocumentChunk。

    Args:
        share_url: ChatGPT 分享連結（https://chatgpt.com/share/{uuid}）

    Returns:
        list[DocumentChunk]，每個對話 turn 為一個 chunk

    Raises:
        ValueError: 連結格式不符、爬取失敗或無學習內容
    """
    if not validate_share_url(share_url):
        raise ValueError(
            f"不符合 ChatGPT 分享連結格式：{share_url}\n"
            "正確格式：https://chatgpt.com/share/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ImportError(
            "Playwright 未安裝。請執行：\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    raw_data = await _fetch_nextdata(share_url)
    messages = _extract_messages(raw_data)
    chunks = _convert_to_chunks(messages, share_url)

    if not chunks:
        raise ValueError(
            "這篇對話沒有學習相關內容（可能是日常閒聊或純生成任務）。"
            "RecallMap 只會保留含學習性問答的對話。"
        )

    return chunks


# ── 內部函式 ──────────────────────────────────────────────────────────────────

async def _fetch_nextdata(share_url: str) -> dict:
    """用 Playwright 開啟頁面，取出 __NEXT_DATA__ JSON"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            # 設定 User-Agent 避免被視為爬蟲封鎖
            await page.set_extra_http_headers({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            })
            await page.goto(share_url, wait_until="networkidle", timeout=30_000)
            raw = await page.evaluate(
                "JSON.parse(document.getElementById('__NEXT_DATA__').textContent)"
            )
        except Exception as e:
            raise ValueError(
                f"無法爬取 ChatGPT 分享頁面：{e}\n"
                "可能原因：連結已失效、需要登入或網路問題。"
            ) from e
        finally:
            await browser.close()

    return raw


def _extract_messages(raw: dict) -> list[dict]:
    """
    從 __NEXT_DATA__ 取出對話訊息列表。
    注意：ChatGPT 改版可能導致路徑變動，需定期確認。
    """
    try:
        # 主要路徑（2024–2025 版本）
        return raw["props"]["pageProps"]["serverResponse"]["data"]["linear_conversation"]
    except (KeyError, TypeError):
        pass

    # 備用路徑嘗試
    try:
        return raw["props"]["pageProps"]["conversation"]["linear_conversation"]
    except (KeyError, TypeError):
        pass

    logger.warning("[chatgpt_share_parser] __NEXT_DATA__ 結構已更新，請更新 parser")
    raise ValueError(
        "無法從頁面解析對話內容（ChatGPT 頁面結構可能已更新）。"
        "請到 GitHub 回報此問題。"
    )


def _convert_to_chunks(messages: list[dict], source_url: str) -> ChunkList:
    """將對話訊息列表轉換成 DocumentChunk，過濾非學習內容"""
    chunks: ChunkList = []

    for i, msg in enumerate(messages):
        try:
            role = msg.get("message", {}).get("author", {}).get("role", "")
            if role not in ("user", "assistant"):
                continue

            content_parts = msg.get("message", {}).get("content", {}).get("parts", [])
            text = " ".join(str(p) for p in content_parts if isinstance(p, str)).strip()

            if not text or len(text) < 20:
                continue

            # 學習對話過濾
            if role == "user":
                if not _is_learning_content(text):
                    continue

            chunks.append(
                DocumentChunk(
                    content=text,
                    source_type=SourceType.CHATGPT,
                    source_id=f"{source_url}::turn-{i}",
                    metadata={
                        "role": role,
                        "turn_index": i,
                        "source_url": source_url,
                    },
                    is_conversation=True,
                    language=_detect_language(text),
                )
            )
        except Exception as e:
            logger.debug(f"[chatgpt_share_parser] 跳過 turn {i}：{e}")

    return chunks


def _is_learning_content(text: str) -> bool:
    """判斷是否為學習相關內容"""
    text_lower = text.lower()
    has_signal = any(sig.lower() in text_lower for sig in _LEARNING_SIGNALS)
    has_exclusion = any(sig.lower() in text_lower for sig in _EXCLUSION_SIGNALS)
    return has_signal and not has_exclusion


def _detect_language(text: str) -> str:
    """簡易語言偵測"""
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return "zh-TW" if cjk_count / max(len(text), 1) > 0.1 else "en"

"""
統一 Gemma 4 呼叫介面
- edge:  Gemma 4 E4B（Ollama 本地，隱私優先）
- cloud: Gemma 4 26B（Vertex AI，實驗室 server，暫為 stub）
"""
import base64
import logging
import os
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

# ── 錯誤類別 ────────────────────────────────────────────────────────────────

class GemmaError(Exception):
    """所有 Gemma 相關錯誤的基礎類別"""


class GemmaEdgeUnavailable(GemmaError):
    """本地 Ollama 不可用"""


class GemmaCloudError(GemmaError):
    """雲端模型呼叫失敗"""


# ── 主類別 ───────────────────────────────────────────────────────────────────

class GemmaClient:
    """
    呼叫方無需知道目前使用邊緣還是雲端模型。
    預設 auto 模式：簡單任務走 edge，複雜任務走 cloud。
    """

    EDGE_MODEL  = "gemma4:e4b"
    CLOUD_MODEL = "gemma-4-26b-it"   # Vertex AI（暫 stub）

    # 簡單任務閾值：prompt 字元數 < 此值 + 無圖片 + 無 tools → 走 edge
    EDGE_MAX_CHARS = 2000

    def __init__(self) -> None:
        self._ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    async def generate(
        self,
        prompt: str,
        images: list[bytes] | None = None,
        mode: Literal["auto", "edge", "cloud"] = "auto",
        tools: list[dict] | None = None,
    ) -> str:
        """
        呼叫 Gemma 4 生成文字。

        Args:
            prompt:  文字提示
            images:  圖片位元組列表（多模態）
            mode:    "auto" | "edge" | "cloud"
            tools:   function calling schema（目前只有 cloud 支援）

        Returns:
            模型生成的純文字回應
        """
        if mode == "auto":
            mode = self._decide_mode(prompt, images, tools)

        if mode == "edge":
            return await self._call_edge(prompt, images)
        else:
            return await self._call_cloud(prompt, images, tools)

    def _decide_mode(
        self,
        prompt: str,
        images: list[bytes] | None,
        tools: list[dict] | None,
    ) -> Literal["edge", "cloud"]:
        """決定使用邊緣或雲端模型"""
        if tools is not None:
            return "cloud"
        if images:
            return "edge"   # E4B 支援多模態，邊緣處理保隱私
        if len(prompt) > self.EDGE_MAX_CHARS:
            return "cloud"
        return "edge"

    async def _call_edge(self, prompt: str, images: list[bytes] | None = None) -> str:
        """呼叫 Ollama 本地 Gemma 4 E4B"""
        url = f"{self._ollama_base}/api/generate"
        payload: dict = {
            "model": self.EDGE_MODEL,
            "prompt": prompt,
            "stream": False,
        }
        if images:
            payload["images"] = [base64.b64encode(img).decode() for img in images]

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "").strip()
        except httpx.ConnectError as e:
            raise GemmaEdgeUnavailable(
                f"無法連線到 Ollama（{self._ollama_base}），請確認 Ollama 已啟動並已下載 {self.EDGE_MODEL}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise GemmaEdgeUnavailable(f"Ollama 回傳錯誤：{e.response.status_code}") from e

    async def _call_cloud(
        self,
        prompt: str,
        images: list[bytes] | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        """
        呼叫 Vertex AI Gemma 4 26B。
        目前為 stub — 實驗室 server 建置完成後實作。
        """
        raise GemmaCloudError(
            "雲端模型尚未設定（實驗室 server 建置中）。"
            "請設定 GOOGLE_CLOUD_PROJECT 等環境變數後再使用 cloud 模式。"
        )

    async def health_check(self) -> dict:
        """回傳 edge / cloud 各自的可用狀態"""
        edge_ok = False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._ollama_base}/api/tags")
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    edge_ok = any(self.EDGE_MODEL in m for m in models)
        except Exception:
            pass

        return {
            "edge": {"available": edge_ok, "model": self.EDGE_MODEL, "url": self._ollama_base},
            "cloud": {"available": False, "model": self.CLOUD_MODEL, "note": "stub — 實驗室 server 建置中"},
        }

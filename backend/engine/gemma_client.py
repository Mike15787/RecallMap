"""
統一 Gemma 4 呼叫介面

支援三種本地 edge backend（透過 EDGE_BACKEND 環境變數切換）：
  - ollama    : Ollama  /api/generate（預設）
  - llamacpp  : llama-server  /v1/chat/completions（OpenAI-compatible）
  - vllm      : vLLM          /v1/chat/completions（OpenAI-compatible）

Cloud backend（Vertex AI）目前為 stub，等實驗室 server 建置後實作。
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
    """本地 inference server 不可用"""


class GemmaCloudError(GemmaError):
    """雲端模型呼叫失敗"""


# ── 型別 ──────────────────────────────────────────────────────────────────────

EdgeBackend = Literal["ollama", "llamacpp", "vllm"]


# ── 主類別 ───────────────────────────────────────────────────────────────────

class GemmaClient:
    """
    呼叫方無需知道目前使用哪個 backend 或 edge/cloud。
    預設 auto 模式：簡單任務走 edge，複雜任務走 cloud。
    """

    # Cloud model（Vertex AI，暫 stub）
    CLOUD_MODEL = "gemma-4-26b-it"

    # 簡單任務閾值：prompt 字元數 < 此值 + 無圖片 + 無 tools → 走 edge
    EDGE_MAX_CHARS = 2000

    def __init__(self) -> None:
        # ── Edge backend 選擇 ──────────────────────────────────────────────
        self._backend: EdgeBackend = os.environ.get("EDGE_BACKEND", "ollama").lower()  # type: ignore[assignment]
        if self._backend not in ("ollama", "llamacpp", "vllm"):
            logger.warning(f"未知的 EDGE_BACKEND={self._backend!r}，退回 ollama")
            self._backend = "ollama"

        # ── Backend 設定 ───────────────────────────────────────────────────
        self._ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model = "gemma4:e4b"

        self._llamacpp_base = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8080")
        self._llamacpp_model = os.environ.get("LLAMACPP_MODEL", "gemma-4")

        self._vllm_base = os.environ.get("VLLM_BASE_URL", "http://localhost:8000")
        self._vllm_model = os.environ.get("VLLM_MODEL", "google/gemma-4-it")

    # ── 公開 API ──────────────────────────────────────────────────────────────

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

    # ── 路由決策 ──────────────────────────────────────────────────────────────

    def _decide_mode(
        self,
        prompt: str,
        images: list[bytes] | None,
        tools: list[dict] | None,
    ) -> Literal["edge", "cloud"]:
        if tools is not None:
            return "cloud"
        if images:
            return "edge"   # 多模態保隱私，走本地
        if len(prompt) > self.EDGE_MAX_CHARS:
            return "cloud"
        return "edge"

    # ── Edge 分派 ─────────────────────────────────────────────────────────────

    async def _call_edge(self, prompt: str, images: list[bytes] | None = None) -> str:
        """依 EDGE_BACKEND 分派到對應的本地 inference server"""
        if self._backend == "ollama":
            return await self._call_ollama(prompt, images)
        elif self._backend == "llamacpp":
            return await self._call_openai_compatible(
                base_url=self._llamacpp_base,
                model=self._llamacpp_model,
                prompt=prompt,
                images=images,
                server_name="llama.cpp",
            )
        else:  # vllm
            return await self._call_openai_compatible(
                base_url=self._vllm_base,
                model=self._vllm_model,
                prompt=prompt,
                images=images,
                server_name="vLLM",
            )

    # ── Ollama ────────────────────────────────────────────────────────────────

    async def _call_ollama(self, prompt: str, images: list[bytes] | None = None) -> str:
        """呼叫 Ollama /api/generate（Ollama 原生格式）"""
        url = f"{self._ollama_base}/api/generate"
        payload: dict = {
            "model": self._ollama_model,
            "prompt": prompt,
            "stream": False,
        }
        if images:
            payload["images"] = [base64.b64encode(img).decode() for img in images]

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json().get("response", "").strip()
        except httpx.ConnectError as e:
            raise GemmaEdgeUnavailable(
                f"無法連線到 Ollama（{self._ollama_base}），"
                f"請確認 Ollama 已啟動並已下載 {self._ollama_model}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise GemmaEdgeUnavailable(
                f"Ollama 回傳錯誤：{e.response.status_code}"
            ) from e

    # ── llama.cpp / vLLM（OpenAI-compatible）─────────────────────────────────

    async def _call_openai_compatible(
        self,
        base_url: str,
        model: str,
        prompt: str,
        images: list[bytes] | None,
        server_name: str,
    ) -> str:
        """
        呼叫 OpenAI-compatible /v1/chat/completions。
        llama.cpp（llama-server）與 vLLM 共用此方法。

        視覺輸入格式（OpenAI vision）：
          content: [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
          ]
        """
        url = f"{base_url}/v1/chat/completions"

        # 組合 content（文字 + 圖片）
        content: list[dict] = [{"type": "text", "text": prompt}]
        if images:
            for img_bytes in images:
                b64 = base64.b64encode(img_bytes).decode()
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except httpx.ConnectError as e:
            raise GemmaEdgeUnavailable(
                f"無法連線到 {server_name}（{base_url}），"
                f"請確認 server 已啟動並載入模型 {model}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise GemmaEdgeUnavailable(
                f"{server_name} 回傳錯誤：{e.response.status_code} — {e.response.text[:200]}"
            ) from e
        except (KeyError, IndexError) as e:
            raise GemmaEdgeUnavailable(
                f"{server_name} 回應格式異常：{e}"
            ) from e

    # ── Cloud（Vertex AI stub）────────────────────────────────────────────────

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

    # ── Health check ──────────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """回傳各 backend 的可用狀態"""
        edge_info = await self._check_edge_health()
        return {
            "active_backend": self._backend,
            "edge": edge_info,
            "cloud": {
                "available": False,
                "model": self.CLOUD_MODEL,
                "note": "stub — 實驗室 server 建置中",
            },
        }

    async def _check_edge_health(self) -> dict:
        if self._backend == "ollama":
            return await self._health_ollama()
        elif self._backend == "llamacpp":
            return await self._health_openai_compatible(
                self._llamacpp_base, self._llamacpp_model, "llama.cpp"
            )
        else:
            return await self._health_openai_compatible(
                self._vllm_base, self._vllm_model, "vLLM"
            )

    async def _health_ollama(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._ollama_base}/api/tags")
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    model_ok = any(self._ollama_model in m for m in models)
                    return {
                        "available": model_ok,
                        "backend": "ollama",
                        "model": self._ollama_model,
                        "url": self._ollama_base,
                    }
        except Exception:
            pass
        return {"available": False, "backend": "ollama", "model": self._ollama_model, "url": self._ollama_base}

    async def _health_openai_compatible(
        self, base_url: str, model: str, backend_name: str
    ) -> dict:
        """llama.cpp 和 vLLM 都有 /v1/models 端點"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{base_url}/v1/models")
                if resp.status_code == 200:
                    model_ids = [m["id"] for m in resp.json().get("data", [])]
                    model_ok = any(model in m for m in model_ids)
                    return {
                        "available": model_ok,
                        "backend": backend_name.lower().replace(".", ""),
                        "model": model,
                        "url": base_url,
                    }
        except Exception:
            pass
        return {
            "available": False,
            "backend": backend_name.lower().replace(".", ""),
            "model": model,
            "url": base_url,
        }

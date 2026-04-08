"""
test_gemma_client.py — mock 各 backend，不呼叫真實 API
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.engine.gemma_client import GemmaClient, GemmaEdgeUnavailable, GemmaCloudError


@pytest.fixture
def client():
    return GemmaClient()


@pytest.fixture
def llamacpp_client(monkeypatch):
    monkeypatch.setenv("EDGE_BACKEND", "llamacpp")
    return GemmaClient()


@pytest.fixture
def vllm_client(monkeypatch):
    monkeypatch.setenv("EDGE_BACKEND", "vllm")
    return GemmaClient()


@pytest.mark.asyncio
async def test_generate_edge_success(client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "這是模型回應"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        result = await client.generate("什麼是遞迴？", mode="edge")
    assert result == "這是模型回應"


@pytest.mark.asyncio
async def test_generate_edge_unavailable(client):
    import httpx
    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with pytest.raises(GemmaEdgeUnavailable):
            await client.generate("test", mode="edge")


@pytest.mark.asyncio
async def test_generate_cloud_raises_stub(client):
    with pytest.raises(GemmaCloudError, match="尚未設定"):
        await client.generate("test", mode="cloud")


def test_decide_mode_short_prompt(client):
    mode = client._decide_mode("短 prompt", None, None)
    assert mode == "edge"


def test_decide_mode_with_tools_goes_cloud(client):
    mode = client._decide_mode("短 prompt", None, [{"name": "create_event"}])
    assert mode == "cloud"


def test_decide_mode_with_images_stays_edge(client):
    mode = client._decide_mode("描述圖片", [b"fake_image"], None)
    assert mode == "edge"


@pytest.mark.asyncio
async def test_health_check_edge_not_available(client):
    import httpx
    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.ConnectError("no ollama")
        )
        health = await client.health_check()
    assert health["edge"]["available"] is False
    assert health["cloud"]["available"] is False
    assert health["active_backend"] == "ollama"


# ── llama.cpp backend ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llamacpp_generate_success(llamacpp_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "llama.cpp 回應"}}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await llamacpp_client.generate("test prompt", mode="edge")
    assert result == "llama.cpp 回應"


@pytest.mark.asyncio
async def test_llamacpp_generate_with_image(llamacpp_client):
    """視覺輸入應包含 image_url content block"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "圖片描述"}}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_http:
        post_mock = AsyncMock(return_value=mock_resp)
        mock_http.return_value.__aenter__.return_value.post = post_mock
        result = await llamacpp_client.generate("描述圖片", images=[b"fake_png"], mode="edge")

    assert result == "圖片描述"
    call_kwargs = post_mock.call_args
    payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
    content = payload["messages"][0]["content"]
    types = [c["type"] for c in content]
    assert "text" in types
    assert "image_url" in types


@pytest.mark.asyncio
async def test_llamacpp_unavailable(llamacpp_client):
    import httpx
    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(GemmaEdgeUnavailable, match="llama.cpp"):
            await llamacpp_client.generate("test", mode="edge")


# ── vLLM backend ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vllm_generate_success(vllm_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "vLLM 回應"}}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await vllm_client.generate("test", mode="edge")
    assert result == "vLLM 回應"


@pytest.mark.asyncio
async def test_vllm_unavailable(vllm_client):
    import httpx
    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(GemmaEdgeUnavailable, match="vLLM"):
            await vllm_client.generate("test", mode="edge")


@pytest.mark.asyncio
async def test_vllm_health_check(vllm_client):
    import httpx
    with patch("httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.ConnectError("no vllm")
        )
        health = await vllm_client.health_check()
    assert health["active_backend"] == "vllm"
    assert health["edge"]["available"] is False


# ── unknown backend fallback ──────────────────────────────────────────────────

def test_unknown_backend_fallback_to_ollama(monkeypatch):
    monkeypatch.setenv("EDGE_BACKEND", "totally_invalid")
    c = GemmaClient()
    assert c._backend == "ollama"

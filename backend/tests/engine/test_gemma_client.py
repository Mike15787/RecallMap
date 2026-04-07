"""
test_gemma_client.py — mock Ollama，不呼叫真實 API
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.engine.gemma_client import GemmaClient, GemmaEdgeUnavailable, GemmaCloudError


@pytest.fixture
def client():
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

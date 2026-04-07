# backend/tests/CLAUDE.md

測試目錄結構與 `backend/` 模組一一對應：

```
tests/
├── ingest/      → 對應 backend/ingest/
├── engine/      → 對應 backend/engine/
└── integrations/→ 對應 backend/integrations/
```

## 執行方式

```bash
# 從 recallmap/ 根目錄執行，需設 PYTHONPATH=.
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/ -v

# 單一模組
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/engine/test_gemma_client.py -v

# 覆蓋率報告
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

## 覆蓋率要求

| 層次 | 最低覆蓋率 |
|------|-----------|
| `ingest/` 所有 parser | 80% |
| `engine/` 核心邏輯 | 70% |
| `integrations/` API 串接 | 60% |
| `api/` 路由 | 70% |

## 規則

- **禁止呼叫真實外部 API**（Notion、Google、Ollama、Vertex AI），一律 mock
- 所有 async 測試使用 `pytest-asyncio`，`pyproject.toml` 已設 `asyncio_mode = "auto"`，不需要在每個測試加 `@pytest.mark.asyncio`
- 測試檔命名：`test_{模組名}.py`

## Mock 範例

```python
# Mock Ollama（GemmaClient）
from unittest.mock import AsyncMock, patch, MagicMock

mock_resp = MagicMock()
mock_resp.json.return_value = {"response": "模型回應"}
mock_resp.raise_for_status = MagicMock()

with patch("httpx.AsyncClient") as mock_http:
    mock_http.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
    result = await client.generate("prompt", mode="edge")

# Mock Notion client
with patch("backend.integrations.notion_api.client") as mock_client:
    mock_client.pages.retrieve = AsyncMock(return_value={...})
```

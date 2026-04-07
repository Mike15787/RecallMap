# backend/CLAUDE.md

Python 3.11+ FastAPI 後端。入口為 `api/main.py`，啟動時會檢查 Ollama edge model 是否就緒。

## 套件管理

依賴定義在 `pyproject.toml`。開發依賴（pytest、ruff）在 `[project.optional-dependencies] dev` 下。

```bash
# 在 backend/ 目錄內安裝
pip install -e ".[dev]"
```

## Session Store

目前使用模組層級的 `dict`（`api/routes/session.py` 的 `_sessions`），重啟後清空。所有路由透過 `get_session_store()` 共用同一份資料。若未來要換成 Redis 或 SQLite，只需改動 `session.py`。

## 層次關係

```
ingest/ → engine/ → api/routes/
              ↑
        integrations/
```

- `ingest/` 把各種格式轉成 `DocumentChunk`
- `engine/` 接收 `DocumentChunk`，輸出盲點、對話、排程
- `integrations/` 供 `engine/` 和 `api/` 呼叫外部服務
- `api/routes/` 組合以上層次，對外暴露 HTTP 端點

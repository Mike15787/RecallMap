# backend/CLAUDE.md

Python 3.11+ FastAPI 後端。入口為 `api/main.py`，啟動時會初始化 llama-cpp-python（`GemmaClient`）並驗證模型檔案可讀。

## 套件管理

依賴定義在 `pyproject.toml`。開發依賴（pytest、ruff）在 `[project.optional-dependencies] dev` 下。

```bash
# 在 backend/ 目錄內安裝
pip install -e ".[dev]"
```

## 資料持久化

SQLite + sqlite-vec。連線與 schema 在 `db/` 下：
- `db/connection.py` — 連線建立、`init_db()` 執行 `CREATE TABLE`
- `db/models.py` — `CREATE_TABLES` 清單（capsules / concepts / concept_chunks / mastery_records / comprehension_events / retention_events / tag 等）

預設資料庫路徑：`~/Documents/RecallMap/recall.db`。

> 仍有歷史程式碼使用 `api/routes/session.py` 的模組層級 `_sessions: dict`。遷移到 SQLite 是未完工項，見 `notes/2026-04-19_架構重訂與設計決策.md`。

## 層次關係

```
ingest/ → engine/ → api/routes/
              ↑         ↑
        integrations/   db/
```

- `ingest/` 把各種格式轉成 `DocumentChunk`
- `engine/` 接收 `DocumentChunk`，輸出概念、分數、題目、排程
- `integrations/` 供 `engine/` 和 `api/` 呼叫外部服務（Notion、Calendar）
- `db/` 由 `engine/` 與 `api/` 共同使用的持久化層
- `api/routes/` 組合以上層次，對外暴露 HTTP 端點（Tauri 前端呼）

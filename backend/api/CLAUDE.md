# backend/api/CLAUDE.md

FastAPI 應用層。`main.py` 是入口，`routes/` 下各檔案負責對應的 HTTP 端點群組。

## main.py

- 啟動時（lifespan）檢查 Ollama edge model 是否可用，不可用時印警告但不中止
- CORS origins 從環境變數 `CORS_ORIGINS` 讀取（預設 `http://localhost:5173`）
- 所有路由掛在 `/v1` 前綴下

## 路由對應

| 檔案 | 前綴 | 功能 |
|------|------|------|
| `routes/session.py` | `/v1/sessions` | 建立、查詢 session |
| `routes/ingest.py` | `/v1/sessions` | 上傳學習材料 |
| `routes/map.py` | `/v1/sessions` | 取得學習地圖、觸發盲點偵測 |
| `routes/schedule.py` | `/v1/schedules` | 建立 SM-2 複習排程 |
| `routes/auth.py` | `/v1/auth` | Google OAuth2 流程 |

## Session Store 共用方式

`session.py` 的模組層級 `_sessions: dict[str, dict]` 是唯一的 session store。其他 route 檔案透過 `from .session import get_session_store` 取得同一份資料，不得自己維護狀態。

Session dict 的結構：
```python
{
    "session_id": str,
    "created_at": str,          # ISO 8601
    "subject": str | None,
    "exam_date": str | None,
    "status": "active",
    "chunks": list[DocumentChunk],
    "blind_spots": list[BlindSpot],
    "learning_map": LearningMap | None,
    "dialogue_sessions": dict,  # blind_spot_id → DialogueSession
    "calendar_credentials": ..., # Google OAuth credentials
}
```

## Ingest 分派邏輯

`routes/ingest.py` 的 `_dispatch()` 依副檔名和 `source_hint` 決定使用哪個 parser：
- `.json` 或 `source_hint=chatgpt/gemini` → chatgpt_parser / gemini_parser
- `.jpg/.jpeg/.png/.webp` → image_parser
- `.pdf/.ppt/.pptx/.doc/.docx` → pdf_parser（需寫暫存檔）
- `/ingest/notion` 端點 → notion_parser

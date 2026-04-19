# backend/api/CLAUDE.md

FastAPI 應用層。`main.py` 是入口，`routes/` 下各檔案負責對應的 HTTP 端點群組。

## main.py

- 啟動時（lifespan）初始化 `GemmaClient`（llama-cpp-python 載入模型），失敗時印警告但不中止以利開發
- CORS origins 從環境變數 `CORS_ORIGINS` 讀取（預設 `http://localhost:1420` — Tauri dev server）
- 所有路由掛在 `/v1` 前綴下

## 路由對應

| 檔案 | 前綴 | 功能 |
|------|------|------|
| `routes/session.py` | `/v1/sessions` | 建立、查詢 session（規劃重命名為 `/v1/capsules`） |
| `routes/ingest.py` | `/v1/sessions/{id}/ingest` | 上傳學習材料 |
| `routes/map.py` | `/v1/sessions/{id}/map` | 取得學習地圖 |
| `routes/quiz.py` | `/v1/quiz` | Quiz session 觸發、作答回報 |
| `routes/topics.py` | `/v1/topics` | 主題 / tag 操作（將與 `routes/session.py` 重整合為 capsule+concept） |
| `routes/schedule.py` | `/v1/schedules` | 建立 SM-2 複習排程 / .ics 匯出 |
| `routes/auth.py` | `/v1/auth` | Google Calendar OAuth2（僅 Calendar，無使用者登入） |

## Session 持久化狀態

**遷移中**：原本是 `session.py` 模組層級 `_sessions: dict`，正在遷移到 SQLite（`backend/db/`）。

- 舊版 dict 結構中包含的欄位如 `chunks`、`blind_spots`、`learning_map`、`dialogue_sessions`、`calendar_credentials`
- 遷移後 `chunks` → `topic_chunks` 表；`mastery_records` 單獨成表；對話 session 已隨 `dialogue.py` 廢棄一併移除
- Calendar credentials 仍需找地方存（Tauri secure storage 或 SQLite 加密欄位），尚未落地

## Ingest 分派邏輯

`routes/ingest.py` 的 `_dispatch()` 依副檔名和 `source_hint` 決定使用哪個 parser：

- `.json` 或 `source_hint=chatgpt/gemini` → chatgpt_parser / gemini_parser
- `.jpg/.jpeg/.png/.webp` → image_parser
- `.pdf/.ppt/.pptx/.doc/.docx` → pdf_parser（需寫暫存檔）
- `/ingest/notion` 端點 → notion_parser
- `/ingest/chatgpt-share` 端點 → chatgpt_share_parser（Playwright）

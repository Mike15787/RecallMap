# RecallMap — 開發指令手冊

> 2026-04-19 架構：桌面單機應用（Tauri + React + Vite）+ Python 後端（FastAPI + llama-cpp-python）
> 所有指令都在 `recallmap/` 根目錄下執行，除非特別標示。

---

## 環境建置

### 1. 後端 — 建立虛擬環境並安裝依賴

```bash
cd backend
python -m venv .venv
```

**Windows：**
```bash
.venv\Scripts\pip install -e ".[dev]"
```

**macOS / Linux：**
```bash
.venv/bin/pip install -e ".[dev]"
```

主要依賴：fastapi、uvicorn、httpx、pydantic、pydantic-settings、python-multipart、
pymupdf、python-pptx、python-docx、pillow、notion-client、google-auth、
google-auth-oauthlib、google-api-python-client、**llama-cpp-python**、**sqlite-vec**、
playwright、pytest、pytest-asyncio、pytest-cov、ruff。

### 2. 下載 Gemma 4 E4B Q4_K_M 模型

放到 `backend/models/gemma-4-e4b-q4_k_m.gguf`。正式版 Tauri 安裝檔會內建此檔；
開發時請自行從 Hugging Face 下載對應 GGUF。

### 3. 設定環境變數

```bash
cp .env.example backend/.env
# 編輯 backend/.env，填入必填項目：
#   LLAMACPP_MODEL_PATH=./models/gemma-4-e4b-q4_k_m.gguf
#   NOTION_TOKEN=...（若要用 Notion 匯入）
#   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET（若要用 Calendar）
```

### 4. 初始化 Playwright（ChatGPT 分享連結爬取用）

```bash
backend/.venv/Scripts/python -m playwright install chromium
```

### 5. 前端 — Tauri + React + Vite

```bash
cd apps/desktop
npm install
```

---

## 啟動開發

### 後端

```bash
# 在 recallmap/ 根目錄
PYTHONPATH=. backend/.venv/Scripts/uvicorn backend.api.main:app --reload --port 8000
```

**macOS / Linux：**
```bash
PYTHONPATH=. backend/.venv/bin/uvicorn backend.api.main:app --reload --port 8000
```

- API 文件：http://localhost:8000/docs
- 健康狀態：http://localhost:8000/health

### 前端（Tauri dev）

```bash
cd apps/desktop
npm run tauri dev
```

第一次會編譯 Rust，耗時數分鐘；之後 hot-reload 很快。

---

## 測試

### 執行所有測試

```bash
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/ -v
```

### 執行特定模組測試

```bash
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/ingest/ -v
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/engine/ -v
```

### 覆蓋率報告

```bash
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

---

## 程式碼格式檢查

```bash
backend/.venv/Scripts/ruff check backend/           # 檢查
backend/.venv/Scripts/ruff check backend/ --fix     # 自動修正

cd apps/desktop && npm run lint                     # 前端
```

---

## 手動 API 測試（curl）

> Session 路由仍以 `/v1/sessions` 為前綴，尚未重命名為 `/v1/capsules`。
> 重命名計畫見 `notes/2026-04-19_架構重訂與設計決策.md`。

### 建立 Session（= Capsule）

```bash
curl -X POST http://localhost:8000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"subject": "資料結構", "exam_date": "2026-05-10T00:00:00+08:00"}'
```

### 上傳 ChatGPT 對話

```bash
curl -X POST http://localhost:8000/v1/sessions/{session_id}/ingest \
  -F "file=@conversations.json" -F "source_hint=chatgpt"
```

### 上傳 PDF 講義

```bash
curl -X POST http://localhost:8000/v1/sessions/{session_id}/ingest \
  -F "file=@lecture.pdf"
```

### 上傳手寫筆記圖片

```bash
curl -X POST http://localhost:8000/v1/sessions/{session_id}/ingest \
  -F "file=@notes.jpg"
```

### 從 Notion 匯入

```bash
curl -X POST http://localhost:8000/v1/sessions/{session_id}/ingest/notion \
  -F "page_id=your-notion-page-id"
```

### 取得學習地圖

```bash
curl http://localhost:8000/v1/sessions/{session_id}/map
```

### 建立複習排程

```bash
curl -X POST http://localhost:8000/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-xxxxxxxxxxxx", "exam_date": "2026-05-10T00:00:00+08:00"}'
```

---

## Git 分支操作（依規格書）

```bash
# 從 develop 切新功能分支
git checkout develop
git checkout -b feat/RM-{ticket}-{description}

# 完成後 PR 回 develop
git push origin feat/RM-{ticket}-{description}
```

---

## 打包 Tauri 安裝檔

```bash
cd apps/desktop
npm run tauri build
```

產物：`apps/desktop/src-tauri/target/release/bundle/` 下的 `.msi`（Windows）、`.dmg`（macOS）。
Gemma 4 E4B Q4_K_M GGUF 必須內建到 bundle 裡（~3GB）。

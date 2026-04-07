# RecallMap — 開發指令手冊

> 所有指令都在 `recallmap/` 根目錄下執行，除非特別標示。

---

## 環境建置

### 1. 建立虛擬環境並安裝依賴

```bash
cd backend
python -m venv .venv
```

**Windows：**
```bash
.venv\Scripts\pip install fastapi uvicorn httpx pydantic pydantic-settings python-multipart pymupdf python-pptx python-docx pillow notion-client google-auth google-auth-oauthlib google-api-python-client pytest pytest-asyncio pytest-cov ruff
```

**macOS / Linux：**
```bash
.venv/bin/pip install fastapi uvicorn httpx pydantic pydantic-settings python-multipart pymupdf python-pptx python-docx pillow notion-client google-auth google-auth-oauthlib google-api-python-client pytest pytest-asyncio pytest-cov ruff
```

### 2. 設定環境變數

```bash
cp backend/.env.example backend/.env
# 用編輯器打開 backend/.env，填入以下必填項目：
#   NOTION_TOKEN=secret_xxxx
#   GOOGLE_CLIENT_ID=...
#   GOOGLE_CLIENT_SECRET=...
```

### 3. 下載 Gemma 4 E4B（Ollama 邊緣模型）

```bash
ollama pull gemma4:e4b
```

確認模型已下載：
```bash
ollama list
```

---

## 啟動開發 Server

```bash
# 在 recallmap/ 根目錄
PYTHONPATH=. backend/.venv/Scripts/uvicorn backend.api.main:app --reload --port 8000
```

**macOS / Linux：**
```bash
PYTHONPATH=. backend/.venv/bin/uvicorn backend.api.main:app --reload --port 8000
```

啟動後開啟：
- API 文件（Swagger）：http://localhost:8000/docs
- 健康狀態：http://localhost:8000/health

---

## 測試

### 執行所有測試

```bash
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/ -v
```

### 執行特定模組測試

```bash
# 只跑 ingest 層
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/ingest/ -v

# 只跑 engine 層
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/engine/ -v
```

### 產生覆蓋率報告

```bash
PYTHONPATH=. backend/.venv/Scripts/python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

---

## 程式碼格式檢查

```bash
# 檢查（不修改）
backend/.venv/Scripts/ruff check backend/

# 自動修正
backend/.venv/Scripts/ruff check backend/ --fix
```

---

## 手動 API 測試（curl）

### 建立 Session

```bash
curl -X POST http://localhost:8000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"subject": "資料結構", "exam_date": "2026-05-10T00:00:00+08:00"}'
```

### 上傳 ChatGPT 對話紀錄

```bash
curl -X POST http://localhost:8000/v1/sessions/{session_id}/ingest \
  -F "file=@conversations.json" \
  -F "source_hint=chatgpt"
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

### 取得學習地圖（觸發盲點偵測）

```bash
curl http://localhost:8000/v1/sessions/{session_id}/map
```

### 開始蘇格拉底對話

```bash
# 第一輪（AI 開場）
curl -X POST http://localhost:8000/v1/sessions/{session_id}/turns \
  -H "Content-Type: application/json" \
  -d '{"blind_spot_id": "bs-xxxxxxxx", "user_message": ""}'

# 後續輪次
curl -X POST http://localhost:8000/v1/sessions/{session_id}/turns \
  -H "Content-Type: application/json" \
  -d '{"blind_spot_id": "bs-xxxxxxxx", "user_message": "我的回答..."}'
```

### 建立複習排程（寫入 Google Calendar）

```bash
curl -X POST http://localhost:8000/v1/schedules \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-xxxxxxxxxxxx", "exam_date": "2026-05-10T00:00:00+08:00"}'
```

---

## Ollama 常用指令

```bash
ollama list                    # 列出已下載模型
ollama run gemma4:e4b          # 互動式測試模型
ollama ps                      # 查看正在執行的模型
ollama rm gemma4:e4b           # 刪除模型
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

## 雲端模型（實驗室 Server）— 待補

> 等實驗室 server 建置完成後補充 Vertex AI 相關設定指令。

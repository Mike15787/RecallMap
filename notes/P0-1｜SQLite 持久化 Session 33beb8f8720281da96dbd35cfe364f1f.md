# P0-1｜SQLite 持久化 Session

# 功能描述

把現有的記憶體 `_sessions` dict 替換成 SQLite，讓伺服器重啟後 session 資料仍然存在。

---

# 輸入 / 輸出

|  | 說明 |
| --- | --- |
| **輸入** | 現有所有 API 的操作行為不變（對外介面不動） |
| **輸出** | Session 資料寫入 SQLite，重啟後可讀回 |

---

# 實作範圍

## ✅ 包含

- 在 `backend/` 建立 `database.py`，封裝 SQLite 讀寫邏輯
- 替換 `api/routes/session.py` 的 `_sessions` dict
- Session 的所有欄位持久化：`session_id`、`subject`、`exam_date`、`status`、`chunks`、`blind_spots`、`learning_map`、`dialogue_sessions`、`calendar_credentials`
- `chunks` / `blind_spots` / `learning_map` 等複雜物件用 JSON 序列化存入 TEXT 欄位
- 伺服器啟動時自動建立 DB 檔案（若不存在）

## ❌ 不包含

- 使用者帳號系統（不同使用者隔離）
- 多設備同步
- 資料加密
- 資料庫 migration 機制（Hackathon 階段直接 drop & recreate）
- Redis 或其他外部資料庫

---

# 關鍵技術決策

- 使用 Python 內建的 `sqlite3`，不引入 SQLAlchemy（減少依賴）
- DB 檔案路徑從環境變數 `DB_PATH` 讀取，預設 `backend/recallmap.db`
- `recallmap.db` 加入 `.gitignore`
- 複雜物件（`chunks`、`blind_spots`）序列化：`dataclass` → `dict` → `json.dumps`

---

# 驗收標準

- [ ]  `POST /v1/sessions` 建立 session 後，重啟 server，`GET /v1/sessions/{id}` 仍能拿到資料
- [ ]  上傳材料後重啟，`chunk_count` 仍正確
- [ ]  取得學習地圖後重啟，再次 GET map 回傳相同結果（不重新跑 AI）
- [ ]  DB 檔案不會被 commit 進 git

---

# 相關檔案

- 新建：`backend/database.py`
- 修改：`backend/api/routes/session.py`（替換 `_sessions`）
- 修改：`.env.example`（加 `DB_PATH`）
- 修改：`.gitignore`（加 `*.db`）
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **新 Session 必讀**：先讀 `notes/2026-04-19_架構重訂與設計決策.md`。那是當前基準。
> 這份 CLAUDE.md 與 `notes/📋 專案實作進度追蹤` 中任何衝突，以 2026-04-19 筆記為準。

## 專案概覽

**RecallMap** — Privacy-First 學習 AI Agent，**單機桌面應用**，100% 本機運行。
- 後端：Python 3.11+（FastAPI）+ llama-cpp-python（內建 Gemma 4 E4B Q4_K_M）+ SQLite + sqlite-vec
- 前端：Tauri（Rust 殼） + React + Vite + TypeScript + shadcn/ui + Tailwind
- UI 語言：英文；內容支援任意語言

## 目錄結構

```
recallmap/
├── backend/          # Python/FastAPI 後端（localhost:8000，Tauri 呼 HTTP）
│   ├── ingest/       # 輸入層：各格式解析器 → DocumentChunk
│   ├── engine/       # AI 核心：concept 抽取、雙軸引擎、SM-2、地圖
│   ├── integrations/ # 外部 API：Notion、Google Calendar、.ics 匯出
│   ├── api/          # FastAPI 應用與路由
│   ├── db/           # SQLite schema 與連線（sqlite-vec）
│   └── tests/        # 測試，結構與模組一一對應
├── apps/
│   └── desktop/      # Tauri + React + Vite（唯一前端）
├── docs/
├── notes/            # 設計筆記（含 2026-04-19 架構重訂）
├── .env.example
└── COMMANDS.md       # 開發指令參考
```

**已刪除目錄**：`apps/mobile/`、`packages/shared/`、`frontend/`（舊 Expo 多平台方案已廢棄）。

詳細指令（安裝、啟動、測試、lint）請參閱 **`COMMANDS.md`**。

---

## 核心架構

### 資料三層：Capsule → Concept → Chunk

- **Capsule**：使用者自訂的學習範圍（如「資料結構 2026 春」），**選填 `exam_date`**。有填才觸發 Calendar 排程。
- **Concept**：從 Chunks 抽取的最小學習單位，**跨 capsule 全域 merge**（同名 concept 共用，tag 標出處）。
- **Chunk**：`DocumentChunk`，ingest 層的統一輸出。與 Concept **多對多**關聯。

### 雙軸：理解 × 記憶（兩張地圖 Tab 切換）

- **理解軸**：quiz 作答後由 Gemma 判 no_understanding / partial / solid / deep。
- **記憶軸**：完整 SM-2（interval + easiness + repetitions）。**Concept 需先達 comprehension `solid` 才進 SM-2 排程。**
- UI：兩張獨立力導向圖（react-flow），節點為 concept，邊為 embedding cosine 相似度 > 閾值。

### Quiz 四題型評分

- 簡答 + 填空 → Gemma 判分
- 選擇 + 是非 → 硬比對 + Gemma 補解釋
- Interleaving：同 session 內多 concept 交錯

---

## 統一規範

### 模組三原則

1. **單一職責** — 一個模組只做一件事
2. **統一介面** — 每個 ingest 模組只暴露一個 `process()`，回傳 `list[DocumentChunk]`
3. **獨立可測試** — 不啟動整個應用也能單獨跑測試

### 核心資料格式 — DocumentChunk

所有 ingest 模組的輸出必須是此格式；engine 層只接受此格式輸入。定義在 `backend/ingest/base.py`。

```python
@dataclass
class DocumentChunk:
    content: str
    source_type: SourceType
    source_id: str
    metadata: dict
    is_conversation: bool = False  # True → 來自 AI 對話，blind_spot 訊號分析用
    language: str = "zh-TW"  # 預設值保留，但實務上內容任意語言
```

前端型別自行在 `apps/desktop/src/types/` 定義（無跨平台共用需求，不再有 `packages/shared`）。

### LLM 呼叫規範

- **一律透過 `GemmaClient`**（`backend/engine/gemma_client.py`）。禁止直接呼叫 llama-cpp-python。
- **只有本機**：沒有 cloud 分支，沒有 `mode="cloud"`。`RUNTIME` 註解可簡化或省略。
- `GemmaClient` 暴露三個方法：
  - `generate(prompt, images=None, tools=None)` → 文字生成
  - `embed(text)` → 向量（寫 sqlite-vec）
  - `classify(prompt, choices)` → 結構化分類輸出

### 命名規範

**Python**：檔案/函式 `snake_case`、類別 `PascalCase`、常數 `UPPER_SNAKE_CASE`、私有成員底線前綴

**TypeScript**：元件 `PascalCase`、函式/變數 `camelCase`、介面 `I` 前綴（`IConcept`）、CSS `kebab-case`

**API 路由**：`kebab-case` 名詞複數，版本前綴 `/v1`。Session 相關端點改名為 Capsule（`/v1/capsules/...`）。

**Git Branch / Commit**：
```
feat/RM-{ticket}-{description}
fix/RM-{ticket}-{description}
chore/{description}
docs/{description}
```
Commit：`<type>(<scope>): <description>`（type: feat / fix / refactor / test / docs / chore）

### 測試覆蓋率要求

| 層次 | 最低覆蓋率 |
|------|-----------|
| `ingest/` | 80% |
| `engine/` | 70% |
| `integrations/` | 60%（mock 為主） |
| `api/` | 70% |

測試中**禁止呼叫真實外部 API 或真實 LLM**，一律 `unittest.mock`。

### 錯誤處理

使用專屬例外類別（`GemmaUnavailable`、`CapsuleNotFound` 等），不得讓例外直接拋到使用者介面。

### 環境變數

`.env` 永遠不得 commit；`.env.example` 必須保持更新。Google Cloud / Vertex AI 相關變數已全部移除。

---

## 分支策略

```
main     → 可部署狀態，只接受來自 develop 的 PR
develop  → 整合分支，每週五同步到 main
feat/*   → 從 develop 切出，完成後 PR 回 develop
fix/*    → 從 develop 切出
```

PR 合併前必須：通過 CI、至少一人 review、填寫 PR 描述。

---

## 已廢棄（Deprecated）

不要再實作、討論、或依賴這些：
- `engine/dialogue.py`（蘇格拉底對話，改自適應 quiz）
- `apps/mobile/`、`packages/shared/`、`frontend/`（多平台方案）
- Ollama、Vertex AI、cloud 模式（改 llama-cpp-python 本機）
- Google OAuth 登入/身份驗證（單使用者，只剩 Calendar 授權）
- 「主題分類器」的「主題」概念（改 capsule + concept + tag）

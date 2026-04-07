# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概覽

**RecallMap** — Privacy-First 學習 AI Agent，混合邊緣 + 雲端架構。
後端：Python 3.11+（FastAPI）；前端：TypeScript + Expo（React Native）。

## 目錄結構

```
recallmap/
├── backend/          # Python/FastAPI 後端
│   ├── ingest/       # 輸入層：各格式解析器 → DocumentChunk
│   ├── engine/       # AI 核心：盲點偵測、對話、排程、學習地圖
│   ├── integrations/ # 外部 API：Notion、Google Calendar、OAuth
│   ├── onboarding/   # 引導流程（stub）
│   ├── api/          # FastAPI 應用與路由
│   └── tests/        # 測試，結構與模組一一對應
├── apps/
│   ├── mobile/       # Expo (React Native) → iOS + Android + Web
│   └── desktop/      # Tauri → Windows + macOS（包裝 mobile web build）
├── packages/
│   └── shared/       # 共用 TypeScript 型別 + API client
├── docs/
├── .env.example
└── COMMANDS.md       # 所有開發指令的完整參考
```

詳細指令（安裝、啟動、測試、lint）請參閱 **`COMMANDS.md`**。

---

## 跨平台架構

四個平台（Web / iOS / Android / 桌面）共用最大化程式碼：

| 平台 | 技術 | 說明 |
|------|------|------|
| Web | Expo web 模式 | 與 mobile 同一份程式碼 |
| iOS | Expo + EAS Build | React Native 編譯 |
| Android | Expo + EAS Build | React Native 編譯 |
| 桌面（Win/Mac） | Tauri | 包裝 Expo web build |

**開發優先順序**：Web → Mobile → Desktop

`packages/shared` 是所有平台的共用核心，禁止在各 app 內自行重複定義型別。

---

## 統一規範

### 模組三原則

每個模組必須同時滿足：
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
    is_conversation: bool = False  # True → 來自 AI 對話，影響盲點偵測
    language: str = "zh-TW"
```

前端對應型別定義在 `packages/shared/src/types/`，**禁止在 apps 內重複定義**。

### LLM 呼叫規範

禁止直接呼叫 Ollama 或 Vertex AI，一律透過 `GemmaClient.generate()`（`backend/engine/gemma_client.py`）。

自動路由（`mode="auto"`）：有 `tools` → cloud；有 `images` → edge；prompt > 2000 字元 → cloud；其餘 → edge。

每個 engine 模組頂部必須標註：
```python
# RUNTIME: edge | cloud | auto
```

### 命名規範

**Python**：檔案/函式 `snake_case`、類別 `PascalCase`、常數 `UPPER_SNAKE_CASE`、私有成員底線前綴

**TypeScript**：元件 `PascalCase`、函式/變數 `camelCase`、介面 `I` 前綴（`IBlindSpot`）、CSS `kebab-case`

**API 路由**：`kebab-case` 名詞複數，版本前綴 `/v1`

**Git Branch**：
```
feat/RM-{ticket}-{description}
fix/RM-{ticket}-{description}
chore/{description}
docs/{description}
```

**Commit**：`<type>(<scope>): <description>`（type: feat / fix / refactor / test / docs / chore）

### 測試覆蓋率要求

| 層次 | 最低覆蓋率 |
|------|-----------|
| `ingest/` | 80% |
| `engine/` | 70% |
| `integrations/` | 60%（mock 為主） |
| `api/` | 70% |

測試中**禁止呼叫真實外部 API**，一律 `unittest.mock`。

### 錯誤處理

使用專屬例外類別（`GemmaEdgeUnavailable` 等），不得讓例外直接拋到使用者介面。

### 環境變數

`.env` 永遠不得 commit；`.env.example` 必須保持更新。

---

## 分支策略

```
main     → 可部署狀態，只接受來自 develop 的 PR
develop  → 整合分支，每週五同步到 main
feat/*   → 從 develop 切出，完成後 PR 回 develop
fix/*    → 從 develop 切出
```

PR 合併前必須：通過 CI、至少一人 review、填寫 PR 描述。

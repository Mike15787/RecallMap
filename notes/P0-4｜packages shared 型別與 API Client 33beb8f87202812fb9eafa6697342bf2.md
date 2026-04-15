# P0-4｜packages/shared 型別與 API Client

# 功能描述

建立 `packages/shared`，定義所有平台共用的 TypeScript 型別，以及呼叫後端 API 的 client 函式。所有 app（mobile、desktop）都從這裡 import，不重複定義。

---

# 輸入 / 輸出

|  | 說明 |
| --- | --- |
| **輸入** | 後端現有的 API 回傳格式（JSON） |
| **輸出** | TypeScript 型別定義 + typed API client 函式 |

---

# 實作範圍

## ✅ 包含

**型別（`src/types/index.ts`）**

```tsx
SourceType, ZoneType
ISession
IBlindSpot
IMapNode, ILearningMap
IDialogueTurn
IIngestResult
IScheduleResult
```

**API Client（`src/api/`）**

- `client.ts`：base fetch 函式，讀取 `EXPO_PUBLIC_API_URL`
- `sessions.ts`：`createSession()`、`getSession()`
- `ingest.ts`：`ingestFile()`、`ingestNotion()`
- `map.ts`：`getLearningMap(force?)`、`postTurn()`
- `schedules.ts`：`createSchedule()`
- `auth.ts`：`getGoogleAuthUrl()`

## ❌ 不包含

- 任何 UI 元件
- 狀態管理（Zustand store 在各 app 內定義）
- Node.js / Python 專用工具函式
- 錯誤重試邏輯（保持簡單）

---

# 關鍵技術決策

- 用 `package.json` 的 `exports` 欄位讓 apps 能直接 import
- `apps/mobile/package.json` 用 `"@recallmap/shared": "*"` 引用（workspace）
- 使用 `fetch` 而非 axios（減少依賴，Expo 原生支援）
- 錯誤處理：HTTP 非 2xx 一律拋 `Error`，由各 app 決定如何呈現

---

# 驗收標準

- [ ]  `apps/mobile` 能 `import { ISession } from '@recallmap/shared'` 且有型別提示
- [ ]  `createSession()` 呼叫後回傳正確型別的資料
- [ ]  `getLearningMap(true)` 帶 `force=true` query param
- [ ]  所有函式都有 TypeScript 回傳型別，沒有 `any`

---

# 相關檔案

- 新建：`packages/shared/src/types/index.ts`
- 新建：`packages/shared/src/api/client.ts`
- 新建：`packages/shared/src/api/sessions.ts`
- 新建：`packages/shared/src/api/ingest.ts`
- 新建：`packages/shared/src/api/map.ts`
- 新建：`packages/shared/src/api/schedules.ts`
- 新建：`packages/shared/package.json`
- 修改：`apps/mobile/package.json`（加 workspace 依賴）
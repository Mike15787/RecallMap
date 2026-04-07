# packages/shared/CLAUDE.md

所有平台（Web / iOS / Android / Desktop）共用的 TypeScript 型別定義與 API client。

**禁止在 `apps/` 任何地方重複定義這裡已有的型別或 API 函式。**

## 目錄結構

```
shared/
├── src/
│   ├── types/
│   │   └── index.ts      # 所有共用介面定義
│   └── api/
│       ├── client.ts     # axios / fetch 基礎設定
│       ├── sessions.ts   # /v1/sessions 相關
│       ├── ingest.ts     # /v1/sessions/{id}/ingest 相關
│       ├── map.ts        # /v1/sessions/{id}/map + turns
│       └── schedules.ts  # /v1/schedules 相關
└── package.json
```

## 型別規範

型別名稱對應後端 Pydantic model，用 `I` 前綴：

```typescript
// types/index.ts

export type SourceType = 'pdf' | 'ppt' | 'word' | 'image' | 'notion' | 'chatgpt' | 'gemini'
export type ZoneType = 'known' | 'fuzzy' | 'blind'

export interface IBlindSpot {
  concept: string
  confidence: number      // 0.0–1.0
  evidence: string[]
  repeat_count: number
  blind_spot_id: string
}

export interface IMapNode {
  node_id: string
  concept: string
  zone: ZoneType
  confidence: number
  evidence: string[]
  repeat_count: number
  last_reviewed: string | null
}

export interface ILearningMap {
  session_id: string
  summary: { known: number; fuzzy: number; blind: number }
  nodes: IMapNode[]
}

export interface ISession {
  session_id: string
  created_at: string
  subject: string | null
  exam_date: string | null
  status: string
  chunk_count: number
  blind_spot_count: number
}

export interface IDialogueTurn {
  role: 'assistant' | 'user'
  content: string
  depth: number | null
  is_completed: boolean
}
```

## API Client 規範

base URL 從環境變數讀取，呼叫方不需知道 URL：

```typescript
// api/client.ts
const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, options)
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}
```

每個 API 函式對應一個後端端點，回傳型別明確標注：

```typescript
// api/sessions.ts
export async function createSession(subject?: string, examDate?: string): Promise<ISession> { ... }
export async function getSession(sessionId: string): Promise<ISession> { ... }
```

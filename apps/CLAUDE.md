# apps/CLAUDE.md

前端應用層。**2026-04-19 架構重訂後只有桌面單一 app**。

## 子目錄

| 目錄 | 技術 | 說明 |
|------|------|------|
| `desktop/` | Tauri + React + Vite + shadcn/ui + Tailwind | 唯一前端 |

## 已刪除

- `apps/mobile/`（Expo React Native → iOS/Android/Web 多平台方案）
- 根目錄 `packages/shared/`（跨平台共用型別）
- 根目錄 `frontend/`（舊殘留目錄）

桌面 app **自行在 `apps/desktop/src/types/` 定義 TypeScript 型別**，與後端 Pydantic schema 對齊（人工維護或用 openapi-typescript 自動產生）。

## 平台目標

- Windows（MSI）
- macOS（DMG）

## 技術細節

- **Tauri 殼層**：Rust 寫的殼，負責打開視窗、檔案存取、啟動後端 sidecar
- **React + Vite**：UI 主體
- **shadcn/ui + Tailwind**：設計系統
- **react-flow**：力導向圖（兩張學習地圖）
- **FastAPI 後端**以 HTTP 方式溝通（localhost:8000），**不是** Tauri sidecar（至少目前不是）

## 開發

```bash
cd apps/desktop
npm install
npm run tauri dev
```

---

## Onboarding 策略

**不做**。第一次開 app 直接看到拖曳區 + 「拖 PDF 進來開始」的文案。這是 2026-04-19 的明確決定。

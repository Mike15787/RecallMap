# apps/CLAUDE.md

前端應用層。包含兩個 app，共用 `packages/shared` 的型別與 API client。

## 子目錄

| 目錄 | 技術 | 負責平台 |
|------|------|---------|
| `mobile/` | Expo (React Native) | iOS + Android + Web（三合一） |
| `desktop/` | Tauri | Windows + macOS |

## 平台關係

```
apps/mobile   ─── web build ───→  apps/desktop (Tauri 包裝)
     │
     └── 共同 import ──→  packages/shared (型別 + API client)
```

桌面版不是獨立前端，它是把 mobile 的 web build 打包成原生應用。開發時只需維護 `mobile/`，`desktop/` 只處理 Tauri 殼層與本地系統整合（Ollama 啟動、檔案存取）。

## 開發優先順序

1. `mobile/`（web 模式）— 主力開發目標
2. `mobile/`（RN 模式）— 調整 iOS/Android 元件
3. `desktop/`（Tauri 包裝）— 最後整合

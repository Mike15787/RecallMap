# apps/desktop/CLAUDE.md

Tauri 桌面應用。把 `apps/mobile` 的 web build 包裝成 Windows / macOS 原生程式。

## 架構定位

Tauri 只負責**殼層與本地系統整合**，不自己寫前端 UI。UI 完全來自 mobile 的 web build。

```
apps/mobile (web build 輸出)
        ↓
apps/desktop/src-tauri  ← 只有這裡有 Rust code
        ↓
Windows .exe / macOS .app
```

## 目錄結構

```
desktop/
├── src-tauri/
│   ├── src/
│   │   └── main.rs       # Tauri 入口，定義系統 commands
│   ├── tauri.conf.json   # 指向 mobile web build 的輸出路徑
│   ├── Cargo.toml
│   └── icons/
└── package.json          # scripts: 先 build mobile web, 再 tauri build
```

## 桌面版特有功能（Tauri Commands）

以下功能只有桌面版有，透過 Tauri `invoke()` 呼叫 Rust：

| Command | 功能 |
|---------|------|
| `check_ollama` | 檢查本機 Ollama 是否在執行 |
| `start_ollama` | 啟動 Ollama 進程 |
| `open_file_dialog` | 開啟原生檔案選擇視窗 |
| `read_local_file` | 直接讀取本機檔案（不需上傳） |

Mobile 端呼叫這些功能前，必須先判斷是否在 Tauri 環境：

```typescript
import { invoke } from '@tauri-apps/api/core'

const isTauri = typeof window !== 'undefined' && '__TAURI__' in window

if (isTauri) {
  await invoke('start_ollama')
} else {
  // web / mobile 降級處理：提示使用者手動啟動
}
```

## 建置流程

```bash
# 1. 先 build mobile 的 web 版本
cd apps/mobile && npx expo export --platform web

# 2. Tauri 讀取 web build，打包成桌面 App
cd apps/desktop && npm run tauri build
```

## 注意

- 桌面版後端（FastAPI）需要額外打包或讓使用者自行安裝 Python 環境
- Hackathon 階段：假設使用者本機已有後端在跑，桌面版只是更好的 UI 入口

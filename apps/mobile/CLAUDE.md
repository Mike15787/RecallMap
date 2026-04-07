# apps/mobile/CLAUDE.md

Expo (React Native) 應用。**一份程式碼**同時跑 iOS、Android、Web。

## 技術選擇

- **框架**：Expo（managed workflow）
- **語言**：TypeScript
- **狀態管理**：Zustand
- **路由**：Expo Router（file-based routing）
- **樣式**：NativeWind（Tailwind CSS for React Native）

## 目錄結構

```
mobile/
├── app/                  # Expo Router 頁面（file-based）
│   ├── (tabs)/           # Tab 導覽群組
│   ├── session/[id]/     # Session 相關頁面
│   └── _layout.tsx
├── src/
│   ├── components/       # 可複用 UI 元件
│   │   ├── DialogueView/ # 蘇格拉底對話介面
│   │   ├── LearningMap/  # 學習地圖視覺化
│   │   ├── Onboarding/   # 引導流程
│   │   └── Dashboard/    # 首頁儀表板
│   ├── screens/          # 頁面層級元件（供 app/ 使用）
│   ├── stores/           # Zustand store（每個功能一個 store）
│   └── hooks/            # 共用 React hooks
├── app.json
└── package.json
```

## 平台差異處理

Expo 用 Platform API 處理平台差異，**不得建立平台專屬的平行元件**：

```typescript
import { Platform } from 'react-native'

// 正確：inline 處理
const padding = Platform.OS === 'ios' ? 44 : 24

// 避免：建立重複元件
// DialogueView.ios.tsx + DialogueView.android.tsx  ← 禁止
```

## 與後端的連線

API base URL 從環境變數讀取：
- Web / 開發：`http://localhost:8000`
- Mobile 實機：需要改成電腦的區網 IP（`http://192.168.x.x:8000`）
- 生產：正式 domain

所有 API 呼叫函式定義在 `packages/shared/src/api/`，此目錄只 import，不重新定義。

## UI 語言規範

面向使用者的文字**禁止出現技術術語**（詳見技術規格書第 10 節）：
- 「向量嵌入中...」→「我正在讀你的筆記...」
- 「API 錯誤」→「暫時連不上，請稍後再試」
- 句子結構：「AI 正在 + [動詞] + 你的 + [名詞]」

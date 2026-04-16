# apps/mobile/CLAUDE.md

Expo (React Native) 前端應用。以下規則適用於此目錄下所有元件、頁面與樣式。

---

## 1. 設計系統配色（強制）

整個前端**只允許使用以下四種顏色**，禁止引入任何 Tailwind 預設色（gray、blue、indigo 等）或其他自訂色。

| Token | Hex | 用途 |
|-------|-----|------|
| `rm-deep`  | `#274c5e` | 主背景、頂層容器、按鈕文字（亮底時） |
| `rm-light` | `#dae9f4` | 主要文字、標題、啟用按鈕背景、高亮邊框 |
| `rm-mid`   | `#77919d` | 次要邊框、停用狀態、placeholder、分隔線 |
| `rm-muted` | `#7f9eb2` | 輔助文字、說明文字、互動提示、icon |

### 使用原則

- **背景**：主背景一律 `bg-rm-deep`
- **文字**：主要文字 `text-rm-light`；次要/說明文字 `text-rm-muted`
- **邊框**：靜態邊框 `rm-mid`；focus / 啟用狀態邊框 `rm-light`
- **按鈕**：
  - 啟用：`bg-rm-light` + `text-rm-deep`
  - 停用：`rgba(119,145,157,0.25)` + `color: rm-mid`
- **半透明層**（輸入框背景、卡片）：使用 `rgba(218,233,244,0.07~0.12)` 疊加在深色背景上

### 禁止使用

```tsx
// ❌ 禁止
className="bg-gray-800 text-white border-indigo-500"

// ✅ 正確
className="bg-rm-deep text-rm-light border-rm-mid"
```

---

## 2. 元件規範

### 命名
- 元件檔案：`PascalCase`（`EntryScreen.tsx`、`QuizCard.tsx`）
- 函式 / 變數：`camelCase`
- 介面：`I` 前綴（`IUserStore`、`IQuizCardProps`）

### 樣式優先順序
1. **NativeWind `className`**：能用 token 的一律用 token（`bg-rm-deep`、`text-rm-light`）
2. **`style` prop**：僅用於 NativeWind 無法表達的動態值（`borderColor` 依 focus 切換、`rgba` 透明度）
3. **禁止**：`StyleSheet.create` 與 inline object style 只在無法用上兩者時才允許

### 互動回饋
- 所有可點擊元素必須有 `activeOpacity={0.85}` 或 Pressable 的 pressed 狀態
- Focus 邊框必須從 `rm-mid` 切換到 `rm-light`（見 EntryScreen 的 `focused` 狀態範例）

---

## 3. UI 語言規範（零門檻設計原則）

面向使用者的文字**禁止出現技術術語**：

| 禁止使用 | 改用 |
|----------|------|
| 「向量嵌入中...」 | 「我正在讀你的筆記...」 |
| 「模型推理中」 | 「快好了！」 |
| 「API 錯誤」 | 「暫時連不上，請稍後再試」 |
| 「Session ID」 | 不對使用者顯示 |

進度狀態句型：「AI 正在 + [動詞] + 你的 + [名詞]」

---

## 4. 路由規範

使用 Expo Router file-based routing：

```
app/
├── index.tsx          # 入口頁（使用者名稱輸入）
├── home.tsx           # 主頁儀表板
├── (tabs)/            # Tab 導覽群組（未來擴充）
└── session/[id]/      # Session 相關頁面
```

- 從入口跳轉一律使用 `router.replace()`（避免返回入口）
- 路由參數透過 `useLocalSearchParams()` 取得，不得用全域 state 傳遞路由資料

---

## 5. 狀態管理規範

使用 Zustand，每個功能域一個 store：

```
src/stores/
├── userStore.ts     # 使用者名稱（已實作）
├── sessionStore.ts  # 學習 session 狀態（待實作）
└── quizStore.ts     # 測驗進行狀態（待實作）
```

- 禁止在元件內部用 `useState` 儲存跨頁面需要的狀態
- Store 介面必須有 `I` 前綴（`IUserStore`）

---

## 6. API 呼叫規範

所有 API 函式定義在 `packages/shared/src/api/`，此目錄**只 import，不在 apps/ 內重新定義**。

```tsx
// ✅ 正確
import { createSession } from "@shared/api/sessions";

// ❌ 禁止
async function createSession() { fetch('/v1/sessions', ...) }  // 在 app 內自己實作
```

# backend/engine/CLAUDE.md

AI 核心層。接收 `DocumentChunk` 列表，執行 concept 抽取、雙軸分數管理、quiz 生成與評分、SM-2 排程，並維護兩張學習地圖。

**所有模組都是本機執行**（llama-cpp-python）。2026-04-19 架構重訂後已完全移除 cloud 分支，`RUNTIME` 註解可簡化或省略。

## 模組說明

### `gemma_client.py` — 統一 LLM 介面

所有模組都必須透過此介面呼叫模型，**禁止直接 import llama_cpp**。

```python
client = GemmaClient()
await client.generate(prompt, images=None, tools=None)  # 文字（含 vision）
await client.embed(text)                                 # 向量（寫 sqlite-vec）
await client.classify(prompt, choices)                   # 結構化分類
```

底層使用 `llama-cpp-python`，模型載入由環境變數 `LLAMACPP_MODEL_PATH` 指定。

> **正在遷移**：現有實作仍透過 HTTP 呼叫 Ollama/llama-server/vLLM。改為直接載入 llama-cpp-python 是進行中的工作。

### `blind_spot.py` — 對話訊號分析器

**已重新定位**（2026-04-19）：從「獨立盲點偵測」改為「對話訊號分析器」，輸出給 `comprehension_engine` 作為初始分數依據。

輸入：`ChunkList`（含 `is_conversation` 標記的 chunks）
輸出：每個 concept 的「重複提問次數」「疑惑訊號強度」等訊號，交給下游。

### `learning_map.py` — 兩張學習地圖

**已重新定位**（2026-04-19）：從四色單圖改為**兩張獨立地圖**（理解 / 記憶），Tab 切換。

- 節點 = concept
- 邊 = 兩 concept 的 embedding cosine > 0.75（用 sqlite-vec 查）
- 理解地圖顏色：依 `comprehension_score`（🔴 < 0.4 / 🟡 0.4–0.7 / 🟢 ≥ 0.7）
- 記憶地圖顏色：依 `next_review_due` 與今日距離（🟠 過期 / 🟢 未到期 / ⚪ 未進入 SM-2）

### `comprehension_engine.py` — 理解軸引擎

- 輸入 quiz 回答 → Gemma 判 `no_understanding / partial / solid / deep`
- 更新 `comprehension_score` + `comprehension_level`
- `solid` 以上且非同 session → 觸發 retention_engine 寫入 SM-2 排程

### `retention_engine.py` — 記憶軸（SM-2）

- 完整 SM-2：interval + easiness + repetitions
- **準入條件**：對應 concept 的 `comprehension_level` 需達 `solid`
- 失敗（response_quality < 2）時 `comprehension_score *= 0.95`（輕微連動衰減）

### `quiz_engine.py` — 四題型生成與評分

- 簡答 / 選擇 / 是非 / 填空
- 策略：`comprehension < 0.4` 先選擇/填空；`0.4–0.7` 簡答為主；`> 0.7` 換情境應用題
- Interleaving：記憶型 session 內 3–5 個 concept 交錯
- 評分：簡答+填空 → Gemma 判；選擇+是非 → 硬比對 + Gemma 補解釋

### `session_trigger.py` — Quiz session 觸發器

依優先順序組裝 session：盲點修復 > 到期記憶複習 > 理解深化。
單次 session 上限 10–15 個 concept。

### `knowledge_base.py` — 持久化層

封裝 SQLite（+ sqlite-vec）CRUD。含 capsule、concept、concept_chunks、tag、mastery_records、embedding 等表的操作。

### `scheduler.py` — SM-2 排程整合

配合 `retention_engine` 產出的 `next_review_due`，產生 Google Calendar events 或 .ics 匯出。

### `tag_generator.py`（規劃中）

取代原 `topic_classifier.py`。從 chunk 內容抽出關鍵詞 tag（如「遞迴」「Java」「OO」），供搜尋/過濾/顯示出處。**不決定圖的邊**（邊靠 embedding）。

### `concept_extractor.py`（規劃中）

兩階段 concept 抽取：
1. **ingest 時粗抽**：快速關鍵詞提取
2. **quiz 前精算**：用戶從清單勾選「要學的」後，再用完整 prompt 精化

### 已廢棄 / 標記為 P2

| 模組 | 狀態 |
|---|---|
| `dialogue.py` | **已廢棄**（2026-04-09）。改自適應 quiz 取代蘇格拉底對話。請勿呼叫、勿擴展。 |
| `delayed_confirmation.py` | **P2**，demo 不做。保留檔案但不接入主流程。 |
| `intent_layer.py` | **P2**（Active/Snoozed/Archived），demo 不做。 |
| `topic_classifier.py` | **重構中**：原「主題分類」廢棄，將改寫為 `tag_generator.py`。 |

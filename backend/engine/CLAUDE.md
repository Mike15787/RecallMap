# backend/engine/CLAUDE.md

AI 核心層。接收 `DocumentChunk` 列表，執行盲點偵測、蘇格拉底對話、間隔複習排程，並維護學習地圖狀態。

每個模組頂部必須標註 RUNTIME，代表預設使用哪一層模型：
```python
# RUNTIME: edge   → Gemma 4 E4B（Ollama 本地）
# RUNTIME: cloud  → Gemma 4 26B（Vertex AI，目前為 stub）
# RUNTIME: auto   → 由 gemma_client._decide_mode() 自動決定
```

## 模組說明

### `gemma_client.py` — 統一 LLM 介面（RUNTIME: N/A）

所有模組都必須透過此介面呼叫模型，禁止直接呼叫 Ollama 或 Vertex AI。

```python
await GemmaClient().generate(prompt, images=None, mode="auto", tools=None)
```

自動路由規則：有 `tools` → cloud；有 `images` → edge；prompt > 2000 字元 → cloud；其餘 → edge。

Cloud 目前為 stub，呼叫會拋 `GemmaCloudError`。

### `blind_spot.py` — 盲點偵測（RUNTIME: auto）

輸入：`ChunkList`（含 `is_conversation` 標記的 chunks）  
輸出：`list[BlindSpot]`

流程：chunks 分為筆記 / 對話兩區塊 → 組成 prompt → 呼叫 Gemma → 解析 JSON 回應。
模型回傳 3–7 個盲點，每個含 `concept`、`confidence`（0–1）、`evidence`、`repeat_count`。

### `learning_map.py` — 學習地圖（RUNTIME: edge，純邏輯不呼叫模型）

維護 `LearningMap`（含 `MapNode` 列表）。`ZoneType` 依 confidence 分區：
- ≥ 0.75 → `KNOWN`（已知區）
- ≥ 0.45 → `FUZZY`（模糊區）
- < 0.45 → `BLIND`（盲點區）

`add_blind_spots()` 把 `BlindSpot` 轉成 `MapNode` 並回填 `blind_spot_id`。
`update_node()` 在蘇格拉底對話結束後更新理解程度。

### `dialogue.py` — 蘇格拉底對話（RUNTIME: auto）

蘇格拉底式追問流程，不直接給答案，引導學生自己思考。

- `start_dialogue(concept, background)` → 回傳第一個問題
- `continue_dialogue(concept, history, user_answer)` → 回傳 `(下一個問題, 理解深度 0–1)`

當理解深度 ≥ 0.8 時自動結束對話。每次評估深度用 edge 模型（短 prompt），追問用 auto。

### `scheduler.py` — SM-2 間隔複習排程（RUNTIME: edge，純演算法）

實作 SM-2 演算法（`SM2Card`）。`build_review_schedule()` 根據盲點列表和考試日期產生 `ReviewEvent` 列表。

- 按 confidence 排序（信心越低越早複習）
- 最多排到考試日或 30 天後
- 若有 `free_slots`（Google Calendar 空檔），會嘗試對齊；否則直接用建議時間
- 目前每個盲點最多排兩輪（第一輪立即，第二輪按 SM-2 間隔）

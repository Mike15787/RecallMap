# backend/ingest/CLAUDE.md

輸入層。負責把各種格式的學習材料解析成統一的 `DocumentChunk` 格式。

## 規則

- 每個 parser 只暴露一個公開函式 `process()`，其餘全部加底線前綴（`_parse_page()`）
- `process()` 回傳 `list[DocumentChunk]`，engine 層只接受此格式
- **原則上不呼叫 AI / LLM**；但以下兩個 parser 例外，可直接使用 `GemmaClient`：
  - `pdf_parser.py` — 整頁渲染後送 Gemma 進行視覺理解
  - `image_parser.py` — 圖片多模態辨識

## 模組清單

| 檔案 | 負責解析 | process() 輸入型別 | AI 依賴 |
|------|---------|-------------------|---------|
| `base.py` | 資料類別定義（`DocumentChunk`、`SourceType`、`ChunkList`） | — | — |
| `pdf_parser.py` | PDF 講義、教材 | 檔案路徑 `str \| Path` | ✅ Gemma edge（整頁渲染）|
| `image_parser.py` | 手寫筆記、截圖 | `bytes`（圖片原始資料） | ✅ Gemma edge |
| `chatgpt_parser.py` | ChatGPT 匯出 JSON | `list[dict] \| dict` | ❌ |
| `gemini_parser.py` | Gemini 匯出 JSON | `list[dict] \| dict` | ❌ |
| `notion_parser.py` | Notion page（透過 API 拉取） | page ID `str` | ❌ |

> **PPT / DOCX**：`pdf_parser.py` 也包含 PPT / DOCX 的文字提取（`_parse_pptx`、`_parse_docx`），
> 但這兩種格式的**圖片 shape 不做 AI 辨識**，純文字提取。
> PPT 視覺理解排程在 P2，待 demo 後再做。

## PDF 解析策略（整頁渲染）

與閉源模型（Claude、GPT-4o、Gemini）相同路線：

```
每一頁 PDF
  ↓ fitz.Page.get_pixmap(matrix=2x)  → PNG bytes
  ↓ GemmaClient.generate(images=[png], mode="edge")
  ↓ 模型輸出純文字（含圖表描述）
  → DocumentChunk
```

- 渲染比例 `RENDER_SCALE = 2.0`（約 144 DPI），足夠讀清楚文字
- 頁面處理失敗時記錄 warning 並跳過，不中斷整份文件
- **需要 edge model（Ollama / llama.cpp / vLLM）在線**

## 學習對話過濾

`chatgpt_parser` 和 `gemini_parser` 在解析時會過濾非學習對話：

- **保留**（LEARNING_SIGNALS）：「為什麼」「怎麼」「什麼是」「why」「how」「explain」等
- **排除**（EXCLUSION_SIGNALS）：「幫我寫」「生成」「write me」「generate」等

來自對話的 chunk 會設 `is_conversation=True`，影響 `engine/blind_spot.py` 的分析邏輯。

## DocumentChunk 欄位說明

```python
content: str          # 純文字（不得為空）
source_type: SourceType
source_id: str        # 唯一識別碼（不得為空）；對話類通常是 "{conv_id}-turn-{n}"
metadata: dict        # 自由格式：頁碼、時間戳、標題等
is_conversation: bool # 對話紀錄設 True
language: str         # 預設 "zh-TW"
```

# backend/ingest/CLAUDE.md

輸入層。負責把各種格式的學習材料解析成統一的 `DocumentChunk` 格式。

## 規則

- 每個 parser 只暴露一個公開函式 `process()`，其餘全部加底線前綴（`_parse_page()`）
- `process()` 回傳 `list[DocumentChunk]`，engine 層只接受此格式
- **原則上不呼叫 AI / LLM**；但以下 parser 例外，可直接使用 `GemmaClient`：
  - `pdf_parser.py` — 整頁渲染後送 Gemma 進行視覺理解
  - `image_parser.py` — 圖片多模態辨識

## 模組清單

| 檔案 | 負責解析 | process() 輸入型別 | AI 依賴 |
|------|---------|-------------------|---------|
| `base.py` | 資料類別定義（`DocumentChunk`、`SourceType`、`ChunkList`） | — | — |
| `pdf_parser.py` | PDF / PPT / DOCX | 檔案路徑 `str \| Path` | ✅ Gemma vision |
| `document_parser.py` | markdown / 純文字 | 檔案路徑 `str \| Path` | ❌ |
| `image_parser.py` | 手寫筆記、截圖 | `bytes`（圖片原始資料） | ✅ Gemma vision |
| `chatgpt_parser.py` | ChatGPT Takeout JSON | `list[dict] \| dict` | ❌ |
| `chatgpt_share_parser.py` | ChatGPT 分享連結 URL | `str`（URL） | ❌（用 Playwright） |
| `gemini_parser.py` | Gemini Takeout JSON | `list[dict] \| dict` | ❌ |
| `notion_parser.py` | Notion page | page ID `str` | ❌ |

> **PPT / DOCX**：`pdf_parser.py` 也包含 PPT / DOCX 的文字提取，但圖片 shape 不做 AI 辨識（純文字提取）。

## PDF / 圖片視覺理解

與閉源模型（Claude、GPT-4o、Gemini）相同路線：整頁 / 整張圖送入模型看。

```
PDF 每一頁                        圖片 bytes
  ↓ fitz.get_pixmap(matrix=2x)       ↓
  PNG bytes                         PNG bytes
       ↓                              ↓
       GemmaClient.generate(images=[png])
       ↓
  模型輸出純文字 → DocumentChunk
```

- PDF 渲染比例 `RENDER_SCALE = 2.0`（約 144 DPI）
- 頁面 / 圖片處理失敗時記錄 warning 並跳過，不中斷整份文件
- **技術 blocker**：llama-cpp-python 對 Gemma 4 vision 的支援需要確認。若不支援，image_parser 的手寫筆記辨識需改策略（見 `notes/2026-04-19_...`）

## 學習對話過濾

`chatgpt_parser` / `gemini_parser` / `chatgpt_share_parser` 解析時會過濾非學習對話：

- **保留**（LEARNING_SIGNALS）：「為什麼」「怎麼」「什麼是」「why」「how」「explain」等
- **排除**（EXCLUSION_SIGNALS）：「幫我寫」「生成」「write me」「generate」等

來自對話的 chunk 設 `is_conversation=True`，`engine/blind_spot.py`（對話訊號分析器）會特別處理這類 chunk。

## DocumentChunk 欄位說明

```python
content: str           # 純文字（不得為空）
source_type: SourceType
source_id: str         # 唯一識別碼；對話類通常是 "{conv_id}-turn-{n}"
metadata: dict         # 自由格式：頁碼、時間戳、標題等
is_conversation: bool  # 對話紀錄設 True
language: str          # 預設 "zh-TW"，實務上內容任意語言
```

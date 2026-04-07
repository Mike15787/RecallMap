# backend/integrations/CLAUDE.md

外部 API 串接層。封裝 Notion、Google Calendar、OAuth 的細節，讓 engine 和 api 層不需要知道 SDK 的使用方式。

## 模組說明

### `notion_api.py`

使用官方 `notion-client` SDK（`AsyncClient`）。token 必須從環境變數讀取：

```python
client = AsyncClient(auth=os.environ["NOTION_TOKEN"])  # 正確
client = AsyncClient(auth="secret_xxx")                # 禁止
```

**分頁處理**：所有讀取操作必須處理分頁，不得假設單次請求能取得全部資料：

```python
async def get_all_blocks(page_id):
    blocks, cursor = [], None
    while True:
        resp = await client.blocks.children.list(page_id, start_cursor=cursor)
        blocks.extend(resp["results"])
        if not resp["has_more"]: break
        cursor = resp["next_cursor"]
    return blocks
```

### `calendar_api.py`

透過 Google Calendar API 查詢空檔與建立複習事件。Gemma 4 用 function calling 操作 Calendar，tool schema 定義在此檔案的 `CALENDAR_TOOLS` 常數中。

已登記的 tools：
- `create_review_event` — 建立複習事件（必填：title, start_datetime, duration_minutes）
- `get_free_slots` — 查詢指定日期範圍的空檔（必填：start_date, end_date）

**新增 tool 前必須先更新 `CALENDAR_TOOLS` 並在技術規格書登記。**

### `auth_manager.py`

管理 Google OAuth2 授權流程。授權後的 credentials 存放在對應 session 的 `sess["calendar_credentials"]` 中（記憶體，重啟後清空）。

OAuth callback endpoint 為 `GET /v1/auth/callback`（`api/routes/auth.py`）。

## 測試原則

測試中禁止呼叫真實的 Notion / Google API，必須全程 mock：

```python
with patch("backend.integrations.notion_api.client") as mock_client:
    mock_client.pages.retrieve = AsyncMock(return_value={...})
```

# backend/onboarding/CLAUDE.md

使用者引導流程模組。負責新用戶第一次使用時的步驟引導（連接 Notion、授權 Google Calendar、上傳第一份學習材料等）。

## 目前狀態

`flow.py` 和 `steps.py` 目前為 stub，尚未實作業務邏輯。

## 預期設計

- `steps.py` — 定義各引導步驟的資料結構與完成條件
- `flow.py` — 管理引導流程的狀態機（哪個步驟已完成、下一步是什麼）

引導完成後應建立一個初始 session，並引導使用者上傳第一份材料進入 `ingest/` 流程。

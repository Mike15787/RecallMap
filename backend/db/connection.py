"""
SQLite 連線管理
提供 get_db() async context manager 和 init_db() 初始化函式。
DB 路徑與 api/store.py 共用同一個環境變數 DATABASE_PATH。
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

logger = logging.getLogger(__name__)

_DB_PATH: str = os.environ.get("DATABASE_PATH", "./recallmap.db")


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """
    取得 SQLite 連線的 async context manager。
    每次呼叫開啟新連線、用完自動關閉。

    Usage:
        async with get_db() as db:
            await db.execute(...)
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db() -> None:
    """
    建立所有知識庫資料表（如尚未存在）。
    應在應用啟動時（lifespan）呼叫一次。
    """
    from .models import CREATE_TABLES

    async with get_db() as db:
        for sql in CREATE_TABLES:
            await db.execute(sql)
        await db.commit()

    logger.info(f"知識庫資料表初始化完成：{_DB_PATH}")

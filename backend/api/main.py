"""
RecallMap FastAPI 主程式
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import ingest, session, schedule, map as map_router, auth, topics, quiz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 Session Store（SQLite）
    from backend.api.store import session_store
    await session_store.init()
    logger.info(f"✅ SQLite Session Store 已就緒：{session_store._db_path}")

    # 初始化知識庫資料表
    from backend.db.connection import init_db
    await init_db()
    logger.info("✅ 知識庫資料表已就緒")

    # 啟動時檢查 LLM backend（非致命，失敗只印警告）
    from backend.engine.gemma_client import GemmaClient
    try:
        client = GemmaClient()
        health = await client.health_check()
        edge = health["edge"]
        if edge.get("available"):
            logger.info(f"[OK] LLM backend ready: {edge.get('backend')} / {edge.get('model')} @ {edge.get('url')}")
        else:
            logger.warning(
                f"[WARN] LLM backend NOT reachable: {edge.get('backend')} @ {edge.get('url')} — "
                f"請確認 server 已啟動、model {edge.get('model')} 已載入"
            )
    except Exception as e:
        logger.warning(f"[WARN] LLM health check 失敗（不中止啟動）：{e}")
    yield


app = FastAPI(
    title="RecallMap API",
    version="0.1.0",
    description="Privacy-First 學習 AI Agent",
    lifespan=lifespan,
)

# CORS
cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:1420",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(session.router,  prefix="/v1/sessions",    tags=["sessions"])
app.include_router(ingest.router,   prefix="/v1/sessions",    tags=["ingest"])
app.include_router(map_router.router, prefix="/v1/sessions",  tags=["map"])
app.include_router(schedule.router, prefix="/v1/schedules",   tags=["schedules"])
app.include_router(auth.router,     prefix="/v1/auth",        tags=["auth"])
app.include_router(topics.router,   prefix="/v1/topics",      tags=["topics"])
app.include_router(quiz.router,     prefix="/v1/topics",      tags=["quiz"])


@app.get("/health")
async def health():
    from backend.engine.gemma_client import GemmaClient
    return await GemmaClient().health_check()

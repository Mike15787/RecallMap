"""
RecallMap FastAPI 主程式
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import ingest, session, schedule, map as map_router, auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 SQLite
    from backend.api.store import session_store
    await session_store.init()
    logger.info(f"✅ SQLite 已就緒：{session_store._db_path}")

    # 啟動時檢查 Ollama 狀態
    from backend.engine.gemma_client import GemmaClient
    client = GemmaClient()
    health = await client.health_check()
    if health["edge"]["available"]:
        logger.info(f"✅ Ollama edge model ready: {health['edge']['model']}")
    else:
        logger.warning(f"⚠️  Ollama edge model NOT available — 請執行: ollama pull {health['edge']['model']}")
    yield


app = FastAPI(
    title="RecallMap API",
    version="0.1.0",
    description="Privacy-First 學習 AI Agent",
    lifespan=lifespan,
)

# CORS
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
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


@app.get("/health")
async def health():
    from backend.engine.gemma_client import GemmaClient
    return await GemmaClient().health_check()

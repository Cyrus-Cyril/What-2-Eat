"""
backend/app/main.py
FastAPI 应用入口 —— 启动命令（在 backend/ 目录下）: uvicorn app.main:app --reload
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import setup_logging, SERVER_HOST, SERVER_PORT
from app.api.routes import router
from app.db.database import init_db, engine

setup_logging()

import logging
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("=" * 50)
    logger.info("What-2-Eat 后端服务启动中...")
    await init_db()
    logger.info(f"API 文档: http://{SERVER_HOST}:{SERVER_PORT}/docs")
    logger.info("=" * 50)
    yield
    # 关闭数据库引擎，确保 aiomysql 的连接池在事件循环关闭前被释放
    try:
        await engine.dispose()
        logger.info("数据库引擎已正确关闭")
    except Exception:
        logger.exception("关闭数据库引擎时发生异常")
    logger.info("What-2-Eat 后端服务已关闭")


app = FastAPI(
    title="今天吃什么 - What-2-Eat API",
    description="基于位置与偏好的智能餐饮推荐系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)

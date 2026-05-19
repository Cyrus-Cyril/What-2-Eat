"""
app/db/database.py
SQLAlchemy 异步引擎 + Session 工厂
"""
import os
import logging
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

logger = logging.getLogger(__name__)

engine = create_async_engine(
    config.DB_URL,
    echo=False,
    pool_size=config.DB_POOL_SIZE,
    max_overflow=config.DB_MAX_OVERFLOW,
    pool_timeout=config.DB_POOL_TIMEOUT,
    pool_recycle=config.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    # 连接归还时强制回滚，避免半途失败的事务污染下次使用
    pool_reset_on_return="rollback",
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """验证数据库连接并串行预热连接池，避免高并发时 aiomysql 并发建连导致包序号错误"""
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("SELECT 1")
        logger.info("数据库连接成功: %s@%s/%s",
                    getattr(config, "DB_USER", ""), 
                    getattr(config, "DB_HOST", ""), 
                    getattr(config, "DB_NAME", ""))
    except SQLAlchemyError as e:
        logger.error("无法连接到数据库。错误: %s", e)
        logger.error("请检查 .env 中的 DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME。")
        return

    # 串行预热连接池：逐个建立 pool_size 条常驻连接
    # 这样在请求到来时连接已存在，不会出现多协程同时建连的 aiomysql 包序号 bug
    conns = []
    try:
        for _ in range(config.DB_POOL_SIZE):
            conn = await engine.connect()
            await conn.execute(text("SELECT 1"))
            conns.append(conn)
        logger.info("连接池预热完成（%d 条连接）", len(conns))
    except Exception as e:
        logger.warning("连接池预热失败（不影响启动）: %s", e)
    finally:
        for conn in conns:
            await conn.close()


@asynccontextmanager
async def get_db():
    """提供异步 Session 的上下文管理器"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

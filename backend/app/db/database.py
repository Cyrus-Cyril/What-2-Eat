"""
app/db/database.py
SQLAlchemy 异步引擎 + Session 工厂
"""
import os
import logging
from contextlib import asynccontextmanager

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
    # MySQL 不需要 check_same_thread
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """验证数据库连接（表已通过 mysql_schema.sql 预先创建）"""
    try:
        async with engine.begin() as conn:
            # 仅做一次 ping，确认连接可用
            await conn.exec_driver_sql("SELECT 1")
        logger.info("数据库连接成功: %s@%s/%s",
                    getattr(config, "DB_USER", ""), 
                    getattr(config, "DB_HOST", ""), 
                    getattr(config, "DB_NAME", ""))
    except SQLAlchemyError as e:
        logger.error("无法连接到数据库。错误: %s", e)
        logger.error("请检查 .env 中的 DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME。")
        return


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

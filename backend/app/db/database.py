"""
app/db/database.py
SQLAlchemy 异步引擎 + Session 工厂
"""
import os
import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

logger = logging.getLogger(__name__)

# 确保 data 目录存在
os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)

engine = create_async_engine(
    config.DB_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """执行 schema.sql 建表（幂等）"""
    sql_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "sql", "schema.sql")
    if not os.path.exists(sql_path):
        logger.warning("schema.sql 未找到: %s", sql_path)
        return

    with open(sql_path, encoding="utf-8") as f:
        raw = f.read()

    # 去掉行内注释（-- ...），避免注释中的分号干扰分割
    lines = []
    for line in raw.splitlines():
        stripped = line.split("--")[0]
        lines.append(stripped)
    sql = "\n".join(lines)

    async with engine.begin() as conn:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.exec_driver_sql(stmt)

    logger.info("数据库建表完成: %s", config.DB_PATH)


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

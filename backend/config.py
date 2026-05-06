"""
config.py
集中管理配置，支持环境变量覆盖
"""
import os
import logging
from dotenv import load_dotenv, find_dotenv


# Load .env from project root if present
load_dotenv(find_dotenv())

# ── 高德地图 API ──────────────────────────────────────────
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "6f38295e3f0fe606c75ea136b154db33")
AMAP_SEARCH_URL = os.getenv("AMAP_SEARCH_URL", "https://restapi.amap.com/v5/place/around")
RESTAURANT_TYPE_CODE = os.getenv("RESTAURANT_TYPE_CODE", "050000")
DEFAULT_RADIUS = int(os.getenv("DEFAULT_RADIUS", "1000"))
DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", "20"))

# ── 大模型 API ────────────────────────────────────────────
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_URL = os.getenv("LLM_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-turbo")

# ── 服务端口 ──────────────────────────────────────────────
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# ── Mock 模式 ──────────────────────────────────────────────
USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"

# ── 数据库 ──────────────────────────────────────────────────
#DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "master.db"))
# DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"

#修改数据库连接云端数据库
# ── MySQL 数据库 ───────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "rm-bp1l57h2hust0ld80yo.rwlb.rds.aliyuncs.com")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "manager")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Root@z666")
DB_NAME = os.getenv("DB_NAME", "what_to_eat")

# SQLAlchemy Async URL
DB_URL = (
    f"mysql+asyncmy://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# # 主库（写）
# DB_MASTER_URL = os.getenv("DB_MASTER_URL", "sqlite:///./data/master.db")
# # 从库（读）
# DB_SLAVE_URL = os.getenv("DB_SLAVE_URL", "sqlite:///./data/slave.db")

# ── 日志 ──────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

"""
config.py
集中管理配置，支持环境变量覆盖
"""
import os
import logging
from dotenv import load_dotenv, find_dotenv


# 以 config.py 所在目录为起点向上查找 .env，避免子进程工作目录不一致导致加载失败
_env_path = find_dotenv(
    filename=".env",
    raise_error_if_not_found=False,
    usecwd=False,                     # 从 __file__ 所在目录起搜，而非 cwd
)
load_dotenv(_env_path, override=True)

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
# 优先从 .env 读取数据库连接配置，默认为本地 MySQL what2eat 数据库
# 格式: mysql+aiomysql://user:password@host:port/dbname
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123456")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "what2eat")

DB_URL = os.getenv(
    "DB_URL", 
    f"mysql+aiomysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
# 兼容性变量（如果其他地方用到）
DB_MASTER_URL = DB_URL
DB_SLAVE_URL = DB_URL

# ── 日志 ──────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

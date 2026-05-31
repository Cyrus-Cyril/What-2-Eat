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
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
AMAP_SEARCH_URL = os.getenv("AMAP_SEARCH_URL", "https://restapi.amap.com/v5/place/around")
RESTAURANT_TYPE_CODE = os.getenv("RESTAURANT_TYPE_CODE", "050000")
DEFAULT_RADIUS = int(os.getenv("DEFAULT_RADIUS", "1000"))
DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", "20"))

# ── 大模型 API ────────────────────────────────────────────
# 旧版单 Key（向后兼容，新版优先使用 LLM_PROVIDERS）
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_URL = os.getenv("LLM_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-turbo")


def _parse_provider_slots(
    keys_env: str,
    url_env: str,
    model_env: str,
    url_default: str,
) -> list[dict]:
    """将逗号分隔的 Key 列表展开为多个 (url, key, model) 槽位。"""
    keys_str = os.getenv(keys_env, "")
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    if not keys:
        return []
    url = os.getenv(url_env, url_default)
    model = os.getenv(model_env, "")
    if not model:
        logging.warning("%s 未配置，槽位将使用空模型名，请在 .env 中设置", model_env)
    return [{"url": url, "key": k, "model": model} for k in keys]


# 多 Provider 槽位列表，轮询调度
# 模型名必须在 .env 中通过 LLM_QWEN_MODEL / LLM_DEEPSEEK_MODEL 显式指定
LLM_PROVIDERS: list[dict] = (
    _parse_provider_slots(
        "LLM_QWEN_KEYS", "LLM_QWEN_API_URL", "LLM_QWEN_MODEL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    + _parse_provider_slots(
        "LLM_DEEPSEEK_KEYS", "LLM_DEEPSEEK_API_URL", "LLM_DEEPSEEK_MODEL",
        "https://api.deepseek.com/v1",
    )
)

# 若新配置未填写，回退到旧版单 Key
if not LLM_PROVIDERS and LLM_API_KEY:
    LLM_PROVIDERS = [{"url": LLM_API_URL, "key": LLM_API_KEY, "model": LLM_MODEL}]
# ── 数据库连接池 ─────────────────────────────────────────
# 4个uvicorn worker各自独立连接池，总连接 = workers × (pool_size + max_overflow)
# MySQL默认 max_connections=151，4×(5+5)=40，留足余量
DB_POOL_SIZE     = int(os.getenv("DB_POOL_SIZE",     "5"))    # 每worker常驻连接
DB_MAX_OVERFLOW  = int(os.getenv("DB_MAX_OVERFLOW",  "5"))    # 每worker突发上限
DB_POOL_TIMEOUT  = int(os.getenv("DB_POOL_TIMEOUT",  "5"))    # 等待连接超时（秒），快速失败
DB_POOL_RECYCLE  = int(os.getenv("DB_POOL_RECYCLE",  "1800")) # 连接回收周期（秒）
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

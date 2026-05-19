#redis 配置
import os
from dotenv import load_dotenv

try:
    import redis
except ImportError:
    redis = None

load_dotenv()

_redis_host = os.getenv("REDIS_HOST")
_redis_port = os.getenv("REDIS_PORT")

redis_client = None

if redis is None:
    print("[INFO] 未安装Redis依赖，将使用无缓存模式")
elif _redis_host and _redis_port:
    try:
        redis_client = redis.Redis(
            host=_redis_host,
            port=int(_redis_port),
            username=os.getenv("REDIS_USERNAME"),
            password=os.getenv("REDIS_PASSWORD"),
            db=int(os.getenv("REDIS_DB") or 0),
            decode_responses=True
        )
        redis_client.ping()
    except Exception as e:
        print(f"[WARN] Redis连接失败: {e} (将使用无缓存模式)")
        redis_client = None
else:
    print("[INFO] 未配置Redis，将使用无缓存模式")

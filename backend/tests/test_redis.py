from app.db.redis_client import redis_client

# 写入 Redis
redis_client.set("test", "hello redis")

# 读取 Redis
value = redis_client.get("test")

print(value)

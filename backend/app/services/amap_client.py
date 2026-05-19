"""
负责调用高德地图 API，返回原始餐馆数据
（加入 Redis 缓存）
"""

import asyncio
import json
import logging

import httpx

from config import (
    AMAP_API_KEY,
    AMAP_SEARCH_URL,
    RESTAURANT_TYPE_CODE,
    DEFAULT_RADIUS,
    DEFAULT_PAGE_SIZE,
)

from app.db.redis_client import redis_client

logger = logging.getLogger(__name__)


async def fetch_nearby_restaurants(
    longitude: float,
    latitude: float,
    radius: int = DEFAULT_RADIUS,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict]:
    page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), 25))

    # =========================
    # Redis 缓存 Key
    # =========================
    cache_key = (
        f"nearby:"
        f"{longitude:.3f}:"
        f"{latitude:.3f}:"
        f"{radius}:"
        f"{page_size}"
    )

    # =========================
    # 查询 Redis 缓存
    # =========================
    if redis_client:
        try:
            cached = redis_client.get(cache_key)

            if cached:
                logger.info("附近餐厅 Redis 命中")
                return json.loads(cached)

            logger.info("附近餐厅 Redis 未命中")

        except Exception:
            logger.exception("Redis 查询失败，继续请求高德API")

    # =========================
    # 请求高德 API
    # =========================
    if not AMAP_API_KEY:
        logger.error("未配置 AMAP_API_KEY，无法请求高德API")
        return []

    params = {
        "key": AMAP_API_KEY,
        "location": f"{longitude},{latitude}",
        "radius": radius,
        "types": RESTAURANT_TYPE_CODE,
        "page_size": page_size,
        "show_fields": "business",
    }

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            ) as client:
                response = await client.get(AMAP_SEARCH_URL, params=params)
                response.raise_for_status()
                data = response.json()

            if data.get("status") != "1":
                logger.error("高德API请求失败：%s", data.get("info"))
                return []

            pois = data.get("pois", [])

            # =========================
            # 写入 Redis 缓存
            # TTL = 600秒（10分钟）
            # =========================
            if redis_client:
                try:
                    redis_client.setex(cache_key, 600, json.dumps(pois))
                    logger.info("附近餐厅已写入 Redis")
                except Exception:
                    logger.exception("Redis 写入失败")

            return pois

        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning("高德API请求异常：%s，attempt=%d", e, attempt + 1)
            if attempt == 1:
                logger.error("高德API请求连续失败，返回空结果")
                return []
            await asyncio.sleep(0.2)
        except httpx.HTTPStatusError as e:
            logger.error("高德API HTTP 错误：%s", e)
            return []
        except Exception:
            logger.exception("高德API请求异常")
            return []

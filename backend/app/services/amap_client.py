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
    max_pages: int = 1,
    types: str | None = None,  # 新增：POI类型码，为None时使用默认值
    keywords: str | None = None,  # 新增：搜索关键词，用于精确定位
) -> list[dict]:
    page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), 25))
    max_pages = max(1, min(max_pages, 4))

    # 使用传入的types或默认值
    poi_types = types or RESTAURANT_TYPE_CODE

    # =========================
    # Redis 缓存 Key（包含types和keywords参数，确保不同请求使用不同缓存）
    # =========================
    cache_key = (
        f"nearby:"
        f"{longitude:.3f}:"
        f"{latitude:.3f}:"
        f"{radius}:"
        f"{page_size}:"
        f"{max_pages}:"
        f"{poi_types}"
        f":{keywords or 'none'}"  # 将keywords加入缓存key
    )

    # =========================
    # 查询 Redis 缓存
    # =========================
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                pois = json.loads(cached)
                logger.info("附近餐厅 Redis 命中，共 %d 条", len(pois))
                return pois
            logger.info("附近餐厅 Redis 未命中")
        except Exception:
            logger.exception("Redis 查询失败，继续请求高德API")

    # =========================
    # 请求高德 API（多页拉取）
    # =========================
    if not AMAP_API_KEY:
        logger.error("未配置 AMAP_API_KEY，无法请求高德API")
        return []

    all_pois: list[dict] = []
    seen_ids: set[str] = set()

    async with httpx.AsyncClient(
        timeout=10.0,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
    ) as client:
        for page in range(1, max_pages + 1):
            params = {
                "key": AMAP_API_KEY,
                "location": f"{longitude},{latitude}",
                "radius": radius,
                "types": poi_types,  # 使用动态types
                "keywords": keywords,  # 使用关键词搜索（可选）
                "page": page,
                "offset": page_size,
                "show_fields": "business",
            }

            for attempt in range(2):
                try:
                    response = await client.get(AMAP_SEARCH_URL, params=params)
                    response.raise_for_status()
                    data = response.json()
                    break
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    logger.warning("高德API请求异常：%s，page=%d attempt=%d", e, page, attempt + 1)
                    if attempt == 1:
                        logger.error("高德API page=%d 连续失败，停止拉取", page)
                        data = None
                        break
                    await asyncio.sleep(0.2)
                except httpx.HTTPStatusError as e:
                    logger.error("高德API HTTP 错误 page=%d：%s", page, e)
                    data = None
                    break

            if data is None:
                break

            if data.get("status") != "1":
                logger.error("高德API page=%d 请求失败：%s", page, data.get("info"))
                break

            pois = data.get("pois", [])
            if not pois:
                logger.info("高德API page=%d 无更多数据，停止拉取", page)
                break

            added = 0
            for poi in pois:
                poi_id = poi.get("id", "")
                if poi_id and poi_id not in seen_ids:
                    seen_ids.add(poi_id)
                    all_pois.append(poi)
                    added += 1
            logger.info("高德API page=%d 获取 %d 条，去重后保留 %d 条", page, len(pois), added)

    logger.info("高德API 合计获取 %d 条餐饮POI", len(all_pois))

    # =========================
    # 写入 Redis 缓存（根据搜索类型调整TTL）
    # - 有关键词搜索：TTL=300s（5分钟，关键词结果更动态）
    # - 纯types搜索：TTL=1800s（30分钟，餐饮数据相对稳定）
    # =========================
    if redis_client and all_pois:
        try:
            cache_ttl = 300 if keywords else 1800  # 动态TTL
            redis_client.setex(cache_key, cache_ttl, json.dumps(all_pois))
            logger.info("附近餐厅已写入 Redis (TTL=%ds, keywords=%s)", cache_ttl, bool(keywords))
        except Exception:
            logger.exception("Redis 写入失败")

    return all_pois

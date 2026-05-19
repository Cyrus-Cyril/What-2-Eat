"""
数据入口服务 —— 对外暴露三个函数：
  - prefetch_and_store()      : 从高德 API 拉取 → 写入 Redis + DB，供预取接口调用
  - get_candidates_no_api()   : 仅从 Redis / DB 读取候选餐厅，不调高德 API（推荐引擎专用）
  - get_candidate_restaurants(): 兜底全量路径（含高德 API），仅在前两步均无数据时由推荐引擎使用

USE_MOCK=true 时三个函数均直接返回 mock_data 中的测试数据。
"""
import json
import logging

import config
from app.services.amap_client import fetch_nearby_restaurants
from app.services.data_cleaner import clean_restaurants
from app.models.restaurant import Restaurant
from app.db.redis_client import redis_client

logger = logging.getLogger(__name__)

# 与 amap_client 保持一致的 Redis Key 模板
_NEARBY_KEY = "nearby:{lng:.3f}:{lat:.3f}:{radius}:{page_size}"


def _build_nearby_key(longitude: float, latitude: float, radius: int, page_size: int) -> str:
    return f"nearby:{longitude:.3f}:{latitude:.3f}:{radius}:{page_size}"


async def prefetch_and_store(
    longitude: float,
    latitude: float,
    radius: int = 1000,
    max_count: int = 20,
) -> list[dict]:
    """
    从高德 API 获取周边餐厅，写入 Redis（TTL=600s）并 upsert 到数据库。
    返回清洗后的餐厅列表，供预取接口直接响应给前端。
    """
    if config.USE_MOCK:
        from app.services.mock_data import get_mock_restaurants
        logger.info("USE_MOCK=true，prefetch 使用 Mock 数据")
        return get_mock_restaurants(max_count)

    logger.info(
        "prefetch_and_store (%.6f, %.6f) radius=%dm count=%d",
        longitude, latitude, radius, max_count,
    )
    # fetch_nearby_restaurants 内部已处理 Redis 读/写，这里直接调用
    raw_data = fetch_nearby_restaurants(longitude, latitude, radius, max_count)
    if not raw_data:
        logger.warning("prefetch: 高德 API 未返回数据")
        return []

    restaurants: list[Restaurant] = clean_restaurants(raw_data)
    result = [r.to_dict() for r in restaurants]

    # 异步写入数据库（upsert restaurant + restaurant_tag）
    try:
        from app.db.crud import upsert_restaurants
        await upsert_restaurants(result)
    except Exception:
        logger.exception("prefetch: 写入数据库失败，不影响返回结果")

    logger.info("prefetch_and_store 完成，有效=%d 家", len(result))
    return result


async def get_candidates_no_api(
    longitude: float,
    latitude: float,
    radius: int = 1000,
    max_count: int = 20,
) -> list[dict]:
    """
    仅从 Redis / DB 获取候选餐厅，不调用高德 API。
    推荐引擎专用路径，保证推荐与外部 API 解耦。

    查找顺序：
      1. Redis（与 amap_client 共用 Key，命中则直接清洗返回）
      2. 数据库（Haversine 空间查询）
    若均无数据，返回空列表（推荐引擎将处理无结果逻辑）。
    """
    if config.USE_MOCK:
        from app.services.mock_data import get_mock_restaurants
        return get_mock_restaurants(max_count)

    # ── Step 1: Redis ──────────────────────────────────────
    if redis_client is not None:
        try:
            cache_key = _build_nearby_key(longitude, latitude, radius, max_count)
            cached = redis_client.get(cache_key)
            if cached:
                raw_data = json.loads(cached)
                restaurants = clean_restaurants(raw_data)
                result = [r.to_dict() for r in restaurants]
                logger.info("get_candidates_no_api Redis 命中，共 %d 家", len(result))
                return result
        except Exception:
            logger.warning("get_candidates_no_api Redis 查询失败，降级到 DB")

    # ── Step 2: 数据库 ─────────────────────────────────────
    try:
        from app.db.crud import get_restaurants_near_location
        db_result = await get_restaurants_near_location(longitude, latitude, radius, max_count)
        if db_result:
            logger.info("get_candidates_no_api DB 命中，共 %d 家", len(db_result))
            return db_result
    except Exception:
        logger.warning("get_candidates_no_api DB 查询失败")

    logger.info(
        "get_candidates_no_api (%.4f,%.4f) r=%dm: Redis 和 DB 均无数据，返回空列表",
        longitude, latitude, radius,
    )
    return []


def get_candidate_restaurants(
    longitude: float,
    latitude: float,
    radius: int = 1000,
    max_count: int = 20,
) -> list[dict]:
    """
    兜底同步路径：调用高德 API 获取候选餐厅（含 Redis 缓存）。
    仅在 get_candidates_no_api 返回空且系统需要兜底时调用。
    正常推荐流程不应直接调用此函数。
    """
    logger.info(
        "[fallback] get_candidate_restaurants 调用高德 API (%.6f, %.6f) radius=%dm count=%d",
        longitude, latitude, radius, max_count,
    )

    if config.USE_MOCK:
        from app.services.mock_data import get_mock_restaurants
        logger.info("USE_MOCK=true，使用 Mock 数据")
        return get_mock_restaurants(max_count)

    raw_data = fetch_nearby_restaurants(longitude, latitude, radius, max_count)
    if not raw_data:
        logger.warning("未获取到任何餐馆数据")
        return []

    restaurants: list[Restaurant] = clean_restaurants(raw_data)
    result = [r.to_dict() for r in restaurants]
    logger.info("data_entry(fallback) 完成，有效=%d 条", len(result))
    return result


if __name__ == "__main__":
    import asyncio
    from config import setup_logging
    setup_logging()

    async def _test():
        result = await prefetch_and_store(114.35968, 30.52878, radius=800)
        logger.info("共找到 %d 家餐馆：", len(result))
        for r in result[:5]:
            logger.info(
                "  %s | %s | %dm | 评分:%s | 人均:%s元",
                r["name"], r["category"], r["distance_m"], r["rating"], r["avg_price"],
            )

    asyncio.run(_test())

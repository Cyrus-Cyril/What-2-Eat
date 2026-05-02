"""
数据入口服务 —— 对外暴露 get_candidate_restaurants()
整合 amap_client + data_cleaner，输出结构化餐馆列表
"""
import logging

from app.services.amap_client import fetch_nearby_restaurants
from app.services.data_cleaner import clean_restaurants
from app.models.restaurant import Restaurant

logger = logging.getLogger(__name__)


def get_candidate_restaurants(longitude: float, latitude: float,
                               radius: int = 1000,
                               max_count: int = 20) -> list[dict]:

    logger.info("搜索位置：(%.6f, %.6f) 半径=%dm 数量=%d", longitude, latitude, radius, max_count)

    raw_data = fetch_nearby_restaurants(longitude, latitude, radius, max_count)

    if not raw_data:
        logger.warning("未获取到任何餐馆数据")
        return []

    restaurants: list[Restaurant] = clean_restaurants(raw_data)
    result = [r.to_dict() for r in restaurants]
    logger.info("数据入口完成 有效=%d条", len(result))
    return result


if __name__ == "__main__":
    from config import setup_logging
    setup_logging()

    test_lng = 114.35968
    test_lat = 30.52878

    results = get_candidate_restaurants(test_lng, test_lat, radius=800)

    logger.info("共找到 %d 家餐馆：", len(results))
    for r in results[:5]:
        logger.info(
            "  %s | %s | %dm | 评分:%s | 人均:%s元",
            r["name"], r["category"], r["distance_m"], r["rating"], r["avg_price"],
        )

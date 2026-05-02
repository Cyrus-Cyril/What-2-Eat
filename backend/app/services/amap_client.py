"""
负责调用高德地图 API，返回原始餐馆数据
"""
import logging

import requests
from config import AMAP_API_KEY, AMAP_SEARCH_URL, RESTAURANT_TYPE_CODE, DEFAULT_RADIUS, DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)


def fetch_nearby_restaurants(longitude: float, latitude: float,
                              radius: int = DEFAULT_RADIUS,
                              page_size: int = DEFAULT_PAGE_SIZE) -> list[dict]:
    params = {
        "key": AMAP_API_KEY,
        "location": f"{longitude},{latitude}",
        "radius": radius,
        "types": RESTAURANT_TYPE_CODE,
        "page_size": page_size,
        "show_fields": "business",
    }

    try:
        response = requests.get(AMAP_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "1":
            logger.error("高德API请求失败：%s", data.get("info"))
            return []

        return data.get("pois", [])

    except requests.exceptions.Timeout:
        logger.error("高德API请求超时")
        return []
    except requests.exceptions.RequestException as e:
        logger.error("高德API请求异常：%s", e)
        return []

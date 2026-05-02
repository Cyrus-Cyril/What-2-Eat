"""
把高德返回的原始数据清洗成统一的 Restaurant 对象
"""
import logging

from app.models.restaurant import Restaurant

logger = logging.getLogger(__name__)


def clean_restaurant(raw: dict) -> Restaurant | None:
    name = raw.get("name", "").strip()
    poi_id = raw.get("id", "").strip()
    location = raw.get("location", "")

    if not name or not poi_id or not location:
        return None

    try:
        lng_str, lat_str = location.split(",")
        longitude = float(lng_str)
        latitude = float(lat_str)
    except ValueError:
        return None

    try:
        distance_m = int(raw.get("distance", 0))
    except ValueError:
        distance_m = 0

    category_raw = raw.get("type", "其他")
    category = category_raw.split(";")[-1].strip() if category_raw else "其他"

    business = raw.get("business", {}) or {}
    rating = _parse_float(business.get("rating", "0"))
    avg_price = _parse_float(business.get("cost", "0"))

    address = raw.get("address", "地址未知")
    if isinstance(address, list):
        address = address[0] if address else "地址未知"

    return Restaurant(
        restaurant_id=poi_id,
        name=name,
        category=category,
        distance_m=distance_m,
        rating=rating,
        avg_price=avg_price,
        address=address,
        latitude=latitude,
        longitude=longitude,
    )


def clean_restaurants(raw_list: list[dict]) -> list[Restaurant]:
    results = []
    for raw in raw_list:
        restaurant = clean_restaurant(raw)
        if restaurant is not None:
            results.append(restaurant)

    logger.info("数据清洗 原始=%d条 → 有效=%d条", len(raw_list), len(results))
    return results


def _parse_float(value: str) -> float:
    try:
        return float(value) if value else 0.0
    except (ValueError, TypeError):
        return 0.0

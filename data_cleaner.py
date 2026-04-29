"""
data_cleaner.py
把高德返回的原始数据清洗成统一的 Restaurant 对象
模块核心部分
"""

from restaurant_model import Restaurant


def clean_restaurant(raw: dict) -> Restaurant | None:
    """
    清洗单条原始餐馆数据

    返回 Restaurant 对象；如果数据缺失关键字段则返回 None（表示丢弃这条数据）
    """
    # 1. 检查必要字段
    name = raw.get("name", "").strip()
    poi_id = raw.get("id", "").strip()
    location = raw.get("location", "")  # 格式："116.473,39.993"

    if not name or not poi_id or not location:
        return None  # 关键字段缺失，丢弃

    # 2. 解析经纬度
    try:
        lng_str, lat_str = location.split(",")
        longitude = float(lng_str)
        latitude = float(lat_str)
    except ValueError:
        return None  # 坐标格式异常，丢弃

    # 3. 解析距离（高德返回字符串，单位是米）
    try:
        distance_m = int(raw.get("distance", 0))
    except ValueError:
        distance_m = 0

    # 4. 解析类别（高德可能返回多级，如"餐饮服务;中餐厅;川菜"，取最后一级）
    category_raw = raw.get("type", "其他")
    category = category_raw.split(";")[-1].strip() if category_raw else "其他"

    # 5. 解析评分和价格（在 business 字段里）
    business = raw.get("business", {}) or {}
    rating = _parse_float(business.get("rating", "0"))
    avg_price = _parse_float(business.get("cost", "0"))

    # 6. 地址
    address = raw.get("address", "地址未知")
    if isinstance(address, list):  # 高德偶尔返回列表
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
    """
    批量清洗，过滤掉无效数据，返回干净的 Restaurant 列表
    """
    results = []
    for raw in raw_list:
        restaurant = clean_restaurant(raw)
        if restaurant is not None:
            results.append(restaurant)

    print(f"[清洗] 原始数据 {len(raw_list)} 条 → 有效数据 {len(results)} 条")
    return results


def _parse_float(value: str) -> float:
    """安全地把字符串转为浮点数，失败则返回 0.0"""
    try:
        return float(value) if value else 0.0
    except (ValueError, TypeError):
        return 0.0

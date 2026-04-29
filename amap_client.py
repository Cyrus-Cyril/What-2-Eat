"""
amap_client.py
负责调用高德地图 API，返回原始餐馆数据
"""

import requests
from config import AMAP_API_KEY, AMAP_SEARCH_URL, RESTAURANT_TYPE_CODE, DEFAULT_RADIUS, DEFAULT_PAGE_SIZE


def fetch_nearby_restaurants(longitude: float, latitude: float,
                              radius: int = DEFAULT_RADIUS,
                              page_size: int = DEFAULT_PAGE_SIZE) -> list[dict]:
    """
    调用高德周边搜索接口，获取附近餐馆原始数据

    参数：
        longitude: 用户当前经度
        latitude:  用户当前纬度
        radius:    搜索半径（米）
        page_size: 返回数量上限

    返回：
        原始餐馆列表（每项是高德返回的原始 dict）
        调用失败则返回空列表
    """
    params = {
        "key": AMAP_API_KEY,
        "location": f"{longitude},{latitude}",  # 高德格式是 经度,纬度
        "radius": radius,
        "types": RESTAURANT_TYPE_CODE,
        "page_size": page_size,
        "show_fields": "business",  # 请求返回评分、价格等扩展字段
    }

    try:
        response = requests.get(AMAP_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # 高德返回 status=1 表示成功
        if data.get("status") != "1":
            print(f"[高德API] 请求失败：{data.get('info')}")
            return []

        return data.get("pois", [])

    except requests.exceptions.Timeout:
        print("[高德API] 请求超时，请检查网络")
        return []
    except requests.exceptions.RequestException as e:
        print(f"[高德API] 请求异常：{e}")
        return []

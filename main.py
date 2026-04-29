"""
main.py
整个模块的入口，对外暴露 get_candidate_restaurants() 这一个函数
后端直接调用这个函数就能拿到已清洗的餐馆数据
"""

from amap_client import fetch_nearby_restaurants
from data_cleaner import clean_restaurants
from restaurant_model import Restaurant


def get_candidate_restaurants(longitude: float, latitude: float,
                               radius: int = 1000,
                               max_count: int = 20) -> list[dict]:
    """
    核心对外接口：根据用户位置，返回附近候选餐馆列表

    参数：
        longitude: 用户经度
        latitude:  用户纬度
        radius:    搜索半径（米），默认1000
        max_count: 最多返回几家，默认20

    返回：
        餐馆字典列表（每项字段见 Restaurant 定义）
    """
    # 第一步：调用高德API拿原始数据
    print(f"[主流程] 搜索位置：({longitude}, {latitude})，半径：{radius}m")
    raw_data = fetch_nearby_restaurants(longitude, latitude, radius, max_count)

    if not raw_data:
        print("[主流程] 未获取到任何餐馆数据")
        return []

    # 第二步：清洗数据
    restaurants: list[Restaurant] = clean_restaurants(raw_data)

    # 第三步：转成字典返回（方便后端JSON序列化或存数据库）
    return [r.to_dict() for r in restaurants]


# ── 本地测试用 ──────────────────────────────────────────────
if __name__ == "__main__":
    # 用学校坐标测试
    test_lng = 114.35968
    test_lat = 30.52878

    results = get_candidate_restaurants(test_lng, test_lat, radius=800)

    print(f"\n共找到 {len(results)} 家餐馆：")
    for r in results[:5]:  # 只打印前5条预览
        print(f"  {r['name']} | {r['category']} | {r['distance_m']}m | 评分:{r['rating']} | 人均:{r['avg_price']}元")

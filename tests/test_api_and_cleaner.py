"""
测试数据入口模块的稳定性和异常处理
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.amap_client import fetch_nearby_restaurants
from app.services.data_cleaner import clean_restaurants, clean_restaurant
from app.models.restaurant import Restaurant
from app.services.data_entry import get_candidate_restaurants


def test_normal_case():
    """正常情况：有效坐标"""
    print("=" * 50)
    print("测试1: 正常坐标查询（上海人民广场）")
    results = get_candidate_restaurants(121.473701, 31.230416, radius=800, max_count=20)
    assert len(results) > 0, "应该返回餐馆数据"
    assert all(k in results[0] for k in ["restaurant_id", "name", "category", "distance_m", "rating", "avg_price", "address", "latitude", "longitude"]), "字段应该完整"
    print(f"OK 成功返回 {len(results)} 条数据，字段完整")


def test_invalid_coordinates():
    """异常情况：无效坐标"""
    print("=" * 50)
    print("测试2: 无效坐标（经度超出范围）")
    results = get_candidate_restaurants(200.0, 31.230416)
    print(f"  返回结果: {len(results)} 条（预期可能为空或少量）")


def test_boundary_coordinates():
    """边界情况：中国经纬度边界"""
    print("=" * 50)
    print("测试3: 边界坐标（北京市中心）")
    results = get_candidate_restaurants(116.407396, 39.904666, radius=1000)
    print(f"  返回结果: {len(results)} 条数据")


def test_small_radius():
    """边界情况：极小搜索半径"""
    print("=" * 50)
    print("测试4: 极小搜索半径（50米）")
    results = get_candidate_restaurants(121.473701, 31.230416, radius=50)
    print(f"  返回结果: {len(results)} 条")


def test_large_radius():
    """边界情况：较大搜索半径"""
    print("=" * 50)
    print("测试5: 较大搜索半径（5000米）")
    results = get_candidate_restaurants(121.473701, 31.230416, radius=5000, max_count=30)
    print(f"  返回结果: {len(results)} 条（请求最多30条）")


def test_data_cleaner_edge_cases():
    """测试数据清洗的边界情况"""
    print("=" * 50)
    print("测试6: 数据清洗边界情况")

    raw_missing = {"name": "测试餐馆"}
    result = clean_restaurant(raw_missing)
    assert result is None, "缺少关键字段应该返回None"
    print("  OK 缺失字段处理正确")

    raw_bad_location = {"id": "123", "name": "测试", "location": "invalid"}
    result = clean_restaurant(raw_bad_location)
    assert result is None, "坐标格式异常应该返回None"
    print("  OK 坐标异常处理正确")

    raw_normal = {
        "id": "test123",
        "name": "测试餐馆",
        "location": "116.473,39.993",
        "distance": "500",
        "type": "餐饮服务;中餐厅;川菜",
        "address": "测试路123号",
        "business": {"rating": "4.5", "cost": "50"}
    }
    result = clean_restaurant(raw_normal)
    assert result is not None, "正常数据应该成功解析"
    assert result.category == "川菜", "类别应该取最后一级"
    assert result.rating == 4.5, "评分应该正确解析"
    print("  OK 正常数据解析正确")


def test_restaurant_to_dict():
    """测试 Restaurant 序列化"""
    print("=" * 50)
    print("测试7: Restaurant 序列化")
    r = Restaurant(
        restaurant_id="abc123",
        name="测试餐厅",
        category="川菜",
        distance_m=500,
        rating=4.5,
        avg_price=80.0,
        address="测试路",
        latitude=39.9,
        longitude=116.4
    )
    d = r.to_dict()
    assert isinstance(d, dict), "应该返回字典"
    assert d["name"] == "测试餐厅", "字段值应该正确"
    print(f"  OK to_dict() 正常工作: {d}")


def test_field_completeness():
    """测试返回字段完整性"""
    print("=" * 50)
    print("测试8: 字段完整性检查")
    results = get_candidate_restaurants(121.473701, 31.230416, radius=800, max_count=5)

    required_fields = [
        "restaurant_id",
        "name",
        "category",
        "distance_m",
        "rating",
        "avg_price",
        "address",
        "latitude",
        "longitude"
    ]

    for r in results:
        missing = [f for f in required_fields if f not in r]
        assert not missing, f"缺少字段: {missing}"

    print(f"  OK {len(results)} 条数据字段完整: {required_fields}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("开始测试: 今天吃什么 - 数据入口模块")
    print("=" * 60 + "\n")

    try:
        test_normal_case()
        test_invalid_coordinates()
        test_boundary_coordinates()
        test_small_radius()
        test_large_radius()
        test_data_cleaner_edge_cases()
        test_restaurant_to_dict()
        test_field_completeness()

        print("\n" + "=" * 60)
        print("OK 所有测试通过！数据入口模块运行稳定")
        print("=" * 60)
    except AssertionError as e:
        print(f"\nFAIL 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nFAIL 异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

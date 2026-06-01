"""
深度调试标签匹配问题
"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.models.schemas import PresetRecommendRequest
from app.services.preset_recommender import recommend_by_preset, _tag_check
from app.services.tag_mapper import get_tags

async def debug_tag_matching():
    base_req = PresetRecommendRequest(
        user_id="test-user",
        longitude=114.35968,
        latitude=30.52878,
        distance_preference=2000,
        budget_min=0,
        budget_max=100,
        spicy_preference=0.5,
        sweet_preference=0.5,
        healthy_preference=0.5,
        favorites=[],
        max_count=6,
    )

    print("="*80)
    print("测试1: 火锅标签")
    print("="*80)
    req = base_req.model_copy(update={"preference_tags": ["火锅"]})
    cards = await recommend_by_preset(req)

    print(f"\n返回 {len(cards)} 条:")
    for i, card in enumerate(cards, 1):
        print(f"\n{i}. {card.name}")
        print(f"   category: '{card.category}'")
        print(f"   tags映射结果: {card.tags}")
        print(f"   shared_tags: {card.shared_tags}")
        print(f"   score: {card.score:.4f}")

        # 手动验证标签匹配
        manual_tags = get_tags(card.category)
        has_match = any(t in manual_tags for t in ["火锅"])
        print(f"   [手动验证] get_tags('{card.category}') = {manual_tags}")
        print(f"   [手动验证] 是否匹配'火锅': {has_match}")

    print("\n\n" + "="*80)
    print("直接调用 _tag_check 测试")
    print("="*80)

    test_restaurants = [
        {"name": "老乡鸡", "category": "特色/地方风味餐厅", "amap_type_path": "餐饮服务;中餐厅;特色/地方风味餐厅"},
        {"name": "瑞幸咖啡", "category": "咖啡厅", "amap_type_path": "餐饮服务;咖啡厅;咖啡厅"},
        {"name": "九筒冒菜", "category": "中餐厅", "amap_type_path": "餐饮服务;中餐厅;中餐厅"},
    ]

    test_tag_sets = [
        ["火锅"],
        ["川菜", "辣"],
        ["饮品", "咖啡"],
    ]

    for rest in test_restaurants:
        print(f"\n餐厅: {rest['name']}")
        print(f"  category: '{rest['category']}'")
        print(f"  amap_type_path: '{rest.get('amap_type_path', '')}'")

        for tags in test_tag_sets:
            has_match, shared = _tag_check(rest, tags)
            r_tags = get_tags(rest["category"])
            print(f"  测试标签{tags}:")
            print(f"    get_tags() = {r_tags}")
            print(f"    匹配结果: has_match={has_match}, shared={shared}")

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    asyncio.run(debug_tag_matching())

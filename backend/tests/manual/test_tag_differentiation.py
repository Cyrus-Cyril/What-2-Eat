"""
测试预设推荐：验证不同标签下是否返回相同结果
"""

import asyncio
import json
import sys
sys.path.insert(0, '.')

from app.models.schemas import PresetRecommendRequest
from app.services.preset_recommender import recommend_by_preset

async def test_different_tags():
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

    test_cases = [
        (["火锅"], "火锅标签"),
        (["日料"], "日料标签"),
        (["西餐"], "西餐标签"),
        (["快餐"], "快餐标签"),
        (["川菜", "辣"], "川菜+辣标签"),
    ]

    results = {}
    for tags, desc in test_cases:
        req = base_req.model_copy(update={"preference_tags": tags})
        print(f"\n{'='*60}")
        print(f"测试：{desc} ({tags})")
        print('='*60)

        cards = await recommend_by_preset(req)
        results[desc] = cards

        print(f"返回 {len(cards)} 条推荐：")
        for i, card in enumerate(cards, 1):
            print(f"  {i}. {card.name:15s} | {card.category:10s} | "
                  f"匹配:{card.shared_tags} | 分数:{card.score:.4f}")
            print(f"     理由: {card.reason}")

    print(f"\n\n{'='*60}")
    print("对比分析：检查不同标签下是否推荐相同餐厅")
    print('='*60)

    all_names = {}
    for desc, cards in results.items:
        names = [c.name for c in cards]
        all_names[desc] = set(names)
        print(f"\n{desc}:")
        print(f"  {names}")

    # 检查重叠度
    print(f"\n\n重叠度分析：")
    descriptions = list(results.keys())
    for i in range(len(descriptions)):
        for j in range(i+1, len(descriptions)):
            d1, d2 = descriptions[i], descriptions[j]
            overlap = all_names[d1] & all_names[d2]
            total = len(all_names[d1] | all_names[d2])
            overlap_rate = len(overlap) / max(total, 1) * 100
            print(f"{d1} vs {d2}: 重叠 {len(overlap)} 家 ({overlap_rate:.1f}%)")
            if overlap:
                print(f"  共同餐厅: {list(overlap)}")

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    asyncio.run(test_different_tags())

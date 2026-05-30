"""
专门测试火锅/烧烤标签问题
"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.models.schemas import PresetRecommendRequest
from app.services.preset_recommender import recommend_by_preset

async def test_hotpot_bbq():
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
        (["火锅"], "火锅"),
        (["烧烤"], "烧烤"),
        (["饮品"], "饮品（对照组）"),
    ]

    for tags, desc in test_cases:
        print(f"\n{'='*80}")
        print(f"测试: {desc} - 标签: {tags}")
        print('='*80)

        req = base_req.model_copy(update={"preference_tags": tags})
        cards = await recommend_by_preset(req)

        print(f"\n返回 {len(cards)} 条推荐:\n")
        for i, card in enumerate(cards, 1):
            match_status = "[匹配]" if card.shared_tags else "[不匹配]"
            print(f"{i}. {card.name:30s} | {card.category:20s} | {match_status}")
            print(f"   标签映射: {card.tags}")
            print(f"   匹配标签: {card.shared_tags}")
            print(f"   分数: {card.score:.4f} | 理由: {card.reason}")
            print()

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    asyncio.run(test_hotpot_bbq())

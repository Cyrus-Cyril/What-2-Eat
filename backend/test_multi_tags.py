"""
测试多标签组合场景
"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.models.schemas import PresetRecommendRequest
from app.services.preset_recommender import recommend_by_preset

async def test_multi_tags():
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

    # 多种多标签组合测试
    test_cases = [
        (["火锅", "烧烤"], "火锅+烧烤（同类）"),
        (["日料", "韩餐"], "日料+韩餐（亚洲）"),
        (["咖啡", "奶茶", "饮品"], "咖啡+奶茶+饮品（饮品类）"),
        (["西餐", "快餐"], "西餐+快餐（西式）"),
        (["火锅", "日料", "咖啡"], "火锅+日料+咖啡（跨类）"),
    ]

    print("="*100)
    print(f"测试 {len(test_cases)} 种多标签组合")
    print("="*100)

    for tags, desc in test_cases:
        print(f"\n{'='*80}")
        print(f"测试: {desc} - 标签: {tags}")
        print('='*80)

        req = base_req.model_copy(update={"preference_tags": tags})
        try:
            cards = await recommend_by_preset(req)
            
            matched_count = sum(1 for c in cards if c.shared_tags)
            total_count = len(cards)
            match_rate = matched_count / total_count * 100 if total_count > 0 else 0

            print(f"\n返回 {total_count} 条推荐 | 匹配率: {matched_count}/{total_count} ({match_rate:.1f}%)")
            print("\n推荐详情:")
            for i, card in enumerate(cards, 1):
                match_status = "[匹配]" if card.shared_tags else "[不匹配]"
                print(f"{i}. {card.name:35s} | {card.category:20s} | {match_status}")
                print(f"   匹配标签: {card.shared_tags} | 分数: {card.score:.4f}")

                # 检查是否匹配了所有标签中的至少一个
                if len(tags) > 1 and card.shared_tags:
                    match_ratio = len(card.shared_tags) / len(tags) * 100
                    print(f"   标签覆盖率: {len(card.shared_tags)}/{len(tags)} ({match_ratio:.0f}%)")

        except Exception as e:
            print(f"[错误] {e}")

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    asyncio.run(test_multi_tags())

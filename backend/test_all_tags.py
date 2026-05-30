"""
全面测试所有前端标签的匹配情况
"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.models.schemas import PresetRecommendRequest
from app.services.preset_recommender import recommend_by_preset

async def test_all_tags():
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

    # 最终11个高质量标签（100%或接近100%匹配率）
    all_tags = [
        "火锅", "烧烤", "日料", "韩餐", "西餐", "快餐",
        "面食", "东南亚", "咖啡", "奶茶", "饮品"
    ]

    print("="*100)
    print(f"全面测试 {len(all_tags)} 个标签的匹配情况")
    print("="*100)

    results = {}
    for tag in all_tags:
        req = base_req.model_copy(update={"preference_tags": [tag]})
        try:
            cards = await recommend_by_preset(req)
            matched_count = sum(1 for c in cards if c.shared_tags)
            total_count = len(cards)
            match_rate = matched_count / total_count * 100 if total_count > 0 else 0

            results[tag] = {
                "total": total_count,
                "matched": matched_count,
                "rate": match_rate,
                "avg_score": sum(c.score for c in cards) / total_count if total_count > 0 else 0,
                "sample": cards[0].name if cards else "无结果"
            }

            status = "[正常]" if match_rate >= 80 else "[异常]" if match_rate >= 20 else "[失败]"
            print(f"\n{status} 标签: {tag:6s} | 匹配率: {matched_count}/{total_count} ({match_rate:5.1f}%) | 均分: {results[tag]['avg_score']:.3f}")
            print(f"     示例: {cards[0].name if cards else '无'} | 匹配标签: {cards[0].shared_tags if cards else []}")

        except Exception as e:
            results[tag] = {"error": str(e)}
            print(f"\n[错误] 标签: {tag:6s} | 错误: {e}")

    # 汇总统计
    print("\n" + "="*100)
    print("汇总统计")
    print("="*100)

    normal = [t for t, r in results.items() if isinstance(r, dict) and "error" not in r and r.get("rate", 0) >= 80]
    partial = [t for t, r in results.items() if isinstance(r, dict) and "error" not in r and 20 <= r.get("rate", 0) < 80]
    failed = [t for t, r in results.items() if isinstance(r, dict) and "error" not in r and r.get("rate", 0) < 20]

    print(f"\n✅ 正常 (>=80%): {len(normal)}个 - {normal}")
    print(f"⚠️  部分匹配 (20-80%): {len(partial)}个 - {partial}")
    print(f"❌ 失败 (<20%): {len(failed)}个 - {failed}")

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    asyncio.run(test_all_tags())

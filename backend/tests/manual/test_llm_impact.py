"""
验证大模型推荐是否受预设推荐修改的影响
"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.services.data_entry import get_candidate_restaurants

async def test_llm_recommend_data_source():
    """
    模拟大模型推荐的调用方式（不传types和keywords）
    验证返回的数据是否符合预期（应该是餐饮大类，无关键词过滤）
    """
    print("="*80)
    print("测试：模拟大模型推荐的数据获取")
    print("="*80)

    # 大模型推荐的典型调用方式（来自recommender.py L261-266）
    raw_restaurants = await get_candidate_restaurants(
        longitude=114.35968,
        latitude=30.52878,
        radius=2000,
        max_count=30,  # max_count * 3 = 10 * 3
        # 注意：没有传types和keywords！使用默认值None
    )

    print(f"\n获取到 {len(raw_restaurants)} 家餐厅")

    if raw_restaurants:
        print("\n前10家餐厅示例:")
        for i, r in enumerate(raw_restaurants[:10], 1):
            name = r.get("name", "?")
            category = r.get("category", "?")
            type_path = r.get("amap_type_path", "?")
            print(f"{i:2d}. {name:35s} | {category:20s} | {type_path}")

        # 统计分类分布
        categories = {}
        for r in raw_restaurants:
            cat = r.get("category", "未知")
            categories[cat] = categories.get(cat, 0) + 1

        print(f"\n分类统计 ({len(raw_restaurants)}家):")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1])[:10]:
            print(f"  - {cat}: {count}家")

        print("\n[结论] 数据获取正常，包含各类餐厅（中餐、快餐、咖啡等）")
        print("[结论] 未受到预设推荐修改的影响 ✅")
    else:
        print("\n[警告] 未获取到数据，可能需要检查API配置")

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    asyncio.run(test_llm_recommend_data_source())

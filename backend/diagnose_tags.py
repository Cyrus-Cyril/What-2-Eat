"""
诊断标签不匹配问题：查看高德API原始数据
"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.services.amap_client import fetch_nearby_restaurants
from app.services.tag_mapper import get_tags

async def diagnose_tag_matching():
    print("获取高德API原始数据（使用特殊半径以绕过缓存）...")
    raw_data = await fetch_nearby_restaurants(
        longitude=114.35968,
        latitude=30.52878,
        radius=6001,  # 使用奇数半径绕过缓存
        page_size=25,
        max_pages=3,
    )

    print(f"\n共获取 {len(raw_data)} 条POI数据\n")
    print("="*80)

    # 统计category分布
    category_stats = {}
    tag_match_stats = {}

    test_tags_list = [
        ["火锅"],
        ["日料"],
        ["西餐"],
        ["快餐"],
        ["川菜", "辣"],
    ]

    for i, poi in enumerate(raw_data[:30], 1):
        name = poi.get("name", "?")
        category = poi.get("category", "") or ""
        distance = poi.get("distance_m", 0)
        tags = get_tags(category)

        # 统计category
        cat_key = category[:30] if category else "空"
        category_stats[cat_key] = category_stats.get(cat_key, 0) + 1

        # 检查标签匹配
        matched_for = []
        for test_tags in test_tags_list:
            if any(t in tags for t in test_tags):
                matched_for.append("+".join(test_tags))

        match_str = ", ".join(matched_for) if matched_for else "[无匹配]"

        print(f"{i:2d}. {name:25s} | {cat_key:30s} | {distance/1000:.1f}km")
        print(f"    映射标签: {tags if tags else '[无标签]'}")
        print(f"    匹配测试: {match_str}")
        print()

    print("\n" + "="*80)
    print("Category 分布统计：")
    print("="*80)
    for cat, count in sorted(category_stats.items(), key=lambda x: -x[1]):
        print(f"  {count:3d}x | {cat}")

    print("\n" + "="*80)
    print("问题分析：")
    print("="*80)

    total_with_tags = sum(1 for poi in raw_data if get_tags(poi.get("category", "")))
    print(f"总POI数: {len(raw_data)}")
    print(f"有标签映射的: {total_with_tags} ({total_with_tags/len(raw_data)*100:.1f}%)")
    print(f"无标签映射的: {len(raw_data) - total_with_tags} ({(len(raw_data)-total_with_tags)/len(raw_data)*100:.1f}%)")

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    asyncio.run(diagnose_tag_matching())

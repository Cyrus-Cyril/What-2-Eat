"""
验证扩大搜索范围是否能获取更多样化餐饮
"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.services.amap_client import fetch_nearby_restaurants
from app.services.tag_mapper import get_tags

async def test_larger_radius():
    radii = [2000, 3000, 5000, 8000, 10000]

    for radius in radii:
        print(f"\n{'='*80}")
        print(f"搜索半径: {radius}m ({radius/1000:.1f}km)")
        print('='*80)

        raw_data = await fetch_nearby_restaurants(
            longitude=114.35968,
            latitude=30.52878,
            radius=radius + 100,  # 微调以绕过缓存
            page_size=25,
            max_pages=3,
        )

        print(f"POI数量: {len(raw_data)}")

        # 统计标签分布
        tag_stats = {}
        matchable = 0
        for poi in raw_data:
            type_path = poi.get("type", "") or ""
            tags = get_tags(type_path)
            if tags:
                matchable += 1
            for t in tags:
                tag_stats[t] = tag_stats.get(t, 0) + 1

        print(f"\n有标签映射: {matchable}/{len(raw_data)} ({matchable/len(raw_data)*100:.1f}%)")
        print("\n标签分布:")
        for tag, count in sorted(tag_stats.items(), key=lambda x: -x[1])[:15]:
            print(f"  {count:3d}x {tag}")

        # 检查关键标签是否存在
        key_tags = ["火锅", "川菜", "日料", "西餐", "烧烤", "韩餐"]
        print(f"\n关键标签检查:")
        for kt in key_tags:
            count = tag_stats.get(kt, 0)
            status = "Y" if count > 0 else "N"
            print(f"  {status} {kt}: {count}家")

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    asyncio.run(test_larger_radius())

"""
验证数据流：检查 get_candidate_restaurants 返回的数据结构
"""

import asyncio
import sys
sys.path.insert(0, '.')

from app.services.data_entry import get_candidate_restaurants

async def check_data_flow():
    print("调用 get_candidate_restaurants...")
    result = await get_candidate_restaurants(
        longitude=114.35968,
        latitude=30.52878,
        radius=6002,  # 绕过缓存
        max_count=25,
        max_pages=1,
    )

    print(f"\n返回 {len(result)} 条记录\n")
    print("="*80)

    for i, r in enumerate(result[:5], 1):
        print(f"\n#{i} {r.get('name')}")
        print(f"  category: '{r.get('category', '')}'")
        print(f"  amap_type_path: '{r.get('amap_type_path', '')}'")
        print(f"  所有keys: {list(r.keys())}")

if __name__ == "__main__":
    from config import setup_logging
    setup_logging()
    asyncio.run(check_data_flow())

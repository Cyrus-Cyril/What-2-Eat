"""
查看高德API原始数据完整结构
"""

import asyncio
import sys
import json
sys.path.insert(0, '.')

import httpx

async def check_raw_api_data():
    async with httpx.AsyncClient(timeout=10.0) as client:
        params = {
            "key": "c952b84e48d5a42b3e76c7bc8a217159",
            "location": f"114.35968,30.52878",
            "radius": 2000,
            "types": "050000",
            "page": 1,
            "offset": 3,
        }

        response = await client.get(
            "https://restapi.amap.com/v5/place/around",
            params=params,
        )
        data = response.json()

        print("="*80)
        print("高德API V5 原始响应（前3条POI）：")
        print("="*80)

        pois = data.get("pois", [])
        print(f"\n状态: {data.get('status')}")
        print(f"总数: {data.get('count')}")
        print(f"本次返回: {len(pois)} 条\n")

        for i, poi in enumerate(pois, 1):
            print(f"\n{'='*80}")
            print(f"POI #{i}: {poi.get('name')}")
            print('='*80)
            print(json.dumps(poi, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(check_raw_api_data())

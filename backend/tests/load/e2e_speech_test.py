"""端到端诊断：recommend → result_id → speeches 轮询"""
import asyncio
import httpx

BASE = "http://localhost:8000"


async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        # 1. 标准模式请求
        r = await c.post(
            f"{BASE}/api/recommend",
            json={
                "query": "想吃火锅",
                "longitude": 114.35968,
                "latitude": 30.52878,
                "radius": 1200,
                "max_count": 3,
                "fast_mode": False,
            },
        )
        data = r.json()
        result_id = data.get("result_id")
        recs = data.get("recommendations", [])
        print(f"recommend: code={data['code']}  recs={len(recs)}  result_id={result_id}")
        if recs:
            exp = recs[0].get("explanation") or {}
            print(f"  explanation keys: {list(exp.keys())}")
            print(f"  ai_speech in initial response: {exp.get('ai_speech')}")

        if not result_id:
            print("ERROR: result_id is None — 标准模式未返回 result_id，轮询不会启动")
            return

        # 2. 轮询
        for i in range(10):
            await asyncio.sleep(1.5)
            s = await c.get(f"{BASE}/api/speeches/{result_id}")
            sd = s.json()
            speeches = sd.get("speeches", [])
            print(f"  poll #{i+1}: code={sd['code']}  speeches={speeches}")
            if sd.get("code") == 0 and speeches:
                print("SUCCESS: speeches ready ✓")
                break
        else:
            print("TIMEOUT: speeches never arrived after 15s")


if __name__ == "__main__":
    asyncio.run(main())

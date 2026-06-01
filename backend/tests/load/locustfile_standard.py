"""
locustfile_standard.py
What-2-Eat Locust 压力测试 — 标准模式（LLM意图解析 + AI解释）

使用方法：
  locust -f locustfile_standard.py --headless -u 10 -r 2 --run-time 60s --host http://localhost:8000

Web UI: http://localhost:8089
"""

import random
import json
from locust import HttpUser, task, between, events


STANDARD_PAYLOADS = [
    {
        "name": "火锅",
        "payload": {
            "query": "想吃火锅",
            "longitude": 114.35968, "latitude": 30.52878,
            "radius": 1200, "max_count": 6,
            "budget_min": 60, "budget_max": 100,
            "taste": "火锅", "people_count": 2,
        },
    },
    {
        "name": "快餐",
        "payload": {
            "query": "便宜又快的午饭",
            "longitude": 114.35968, "latitude": 30.52878,
            "radius": 1000, "max_count": 4,
            "budget_min": 20, "budget_max": 40,
            "taste": "快餐", "people_count": 1,
        },
    },
    {
        "name": "烧烤",
        "payload": {
            "query": "想吃烧烤",
            "longitude": 114.35968, "latitude": 30.52878,
            "radius": 1500, "max_count": 5,
            "budget_min": 50, "budget_max": 80,
            "taste": "烧烤", "people_count": 3,
        },
    },
    {
        "name": "日料",
        "payload": {
            "query": "想吃日料",
            "longitude": 114.35968, "latitude": 30.52878,
            "radius": 1000, "max_count": 6,
            "budget_min": 80, "budget_max": 150,
            "taste": "日料", "people_count": 2,
        },
    },
    {
        "name": "咖啡",
        "payload": {
            "query": "想喝咖啡",
            "longitude": 114.35968, "latitude": 30.52878,
            "radius": 800, "max_count": 4,
            "budget_min": 15, "budget_max": 40,
            "taste": "咖啡", "people_count": 1,
        },
    },
]

_ok = 0
_fail = 0


class StandardUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        StandardUser._counter = getattr(StandardUser, "_counter", 0) + 1
        self.user_id = f"std_user_{StandardUser._counter}"
        self.query_idx = random.randint(0, len(STANDARD_PAYLOADS) - 1)

    @task
    def recommend(self):
        global _ok, _fail

        item = STANDARD_PAYLOADS[self.query_idx % len(STANDARD_PAYLOADS)]
        self.query_idx += 1

        payload = dict(item["payload"])
        payload["user_id"] = self.user_id

        with self.client.post(
            "/api/recommend",
            json=payload,
            name=f"标准-{item['name']}",
            catch_response=True,
            timeout=90,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("recommendations"):
                    resp.success()
                    _ok += 1
                else:
                    resp.failure("空结果")
                    _fail += 1
            else:
                resp.failure(f"HTTP {resp.status_code}")
                _fail += 1


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "=" * 60)
    print("  What-2-Eat 压测 — 标准模式（LLM + AI解释）")
    print("  Web UI: http://localhost:8089")
    print("=" * 60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    total = _ok + _fail
    print("\n" + "=" * 60)
    print(f"  标准模式: 成功 {_ok} | 失败 {_fail} | 成功率 {_ok/max(total,1)*100:.1f}%")
    print("=" * 60 + "\n")

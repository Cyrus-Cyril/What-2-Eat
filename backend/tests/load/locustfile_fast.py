"""
locustfile_fast.py
What-2-Eat Locust 压力测试 — 极速模式（跳过LLM，< 1s返回）

使用方法：
  locust -f locustfile_fast.py --headless -u 10 -r 2 --run-time 60s --host http://localhost:8000

Web UI: http://localhost:8089
"""

import json
from locust import HttpUser, task, between, events


FAST_MODE_PAYLOAD = {
    "longitude": 114.35968, "latitude": 30.52878,
    "radius": 1200, "max_count": 6,
    "budget_min": 0, "budget_max": 100,
    "fast_mode": True,
}

_ok = 0
_fail = 0


class FastUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        FastUser._counter = getattr(FastUser, "_counter", 0) + 1
        self.user_id = f"fast_user_{FastUser._counter}"

    @task
    def recommend(self):
        global _ok, _fail

        with self.client.post(
            "/api/recommend",
            json=FAST_MODE_PAYLOAD,
            name="极速模式",
            catch_response=True,
            timeout=15,
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
    print("  What-2-Eat 压测 — 极速模式（跳过LLM）")
    print("  Web UI: http://localhost:8089")
    print("=" * 60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    total = _ok + _fail
    print("\n" + "=" * 60)
    print(f"  极速模式: 成功 {_ok} | 失败 {_fail} | 成功率 {_ok/max(total,1)*100:.1f}%")
    print("=" * 60 + "\n")

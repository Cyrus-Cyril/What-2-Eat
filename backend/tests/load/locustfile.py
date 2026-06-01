"""
locustfile.py
What-2-Eat Locust 并发压力测试

使用方法：
  pip install locust
  locust -f locustfile.py                          # 打开 Web UI: http://localhost:8089
  locust -f locustfile.py --headless -u 20 -r 2    # 无 UI，20用户，每秒2个爬升
  locust -f locustfile.py --headless -u 5 -r 1 --run-time 60s   # 固定运行60秒

Web UI 地址：http://localhost:8089
  - Charts 页：实时 RPS / 响应时间 / 失败率折线图
  - Statistics 页：每个接口的 P50/P90/P99 延迟表格
  - Failures 页：失败详情（状态码 + 错误信息）
  - Download Data：导出 CSV / HTML 报告
"""

import random
import time
import json
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner


# ── 测试数据 ──────────────────────────────────────────────────────────────

# 模拟 5 类真实用户 query
RECOMMEND_PAYLOADS = [
    {
        "name": "火锅查询",
        "payload": {
            "query": "想吃火锅",
            "longitude": 114.35968,
            "latitude": 30.52878,
            "radius": 1200,
            "max_count": 6,
            "budget_min": 60,
            "budget_max": 100,
            "taste": "火锅",
            "people_count": 2,
        },
    },
    {
        "name": "便宜快餐",
        "payload": {
            "query": "便宜又快的午饭",
            "longitude": 114.35968,
            "latitude": 30.52878,
            "radius": 1000,
            "max_count": 4,
            "budget_min": 20,
            "budget_max": 40,
            "taste": "快餐",
            "people_count": 1,
        },
    },
    {
        "name": "川菜辣食",
        "payload": {
            "query": "想吃辣的",
            "longitude": 114.35968,
            "latitude": 30.52878,
            "radius": 1500,
            "max_count": 5,
            "budget_min": 50,
            "budget_max": 80,
            "taste": "川菜",
            "people_count": 3,
        },
    },
    {
        "name": "双人聚餐",
        "payload": {
            "query": "适合两个人一起吃",
            "longitude": 114.35968,
            "latitude": 30.52878,
            "radius": 1000,
            "max_count": 6,
            "budget_min": 80,
            "budget_max": 150,
            "people_count": 2,
        },
    },
    {
        "name": "热乎面食",
        "payload": {
            "query": "想吃热乎一点的",
            "longitude": 114.35968,
            "latitude": 30.52878,
            "radius": 800,
            "max_count": 4,
            "budget_min": 30,
            "budget_max": 60,
            "taste": "面食",
            "people_count": 1,
        },
    },
]

# 反馈请求模板（在推荐后随机提交一次反馈）
FEEDBACK_ACTIONS = ["LIKE", "DISLIKE"]

# 统计：LLM 降级次数（从响应体判断）
_llm_degraded_count = 0
_llm_normal_count = 0


# ── 用户行为类 ────────────────────────────────────────────────────────────

class RecommendUser(HttpUser):
    """
    普通推荐用户：
    - 80% 概率发推荐请求（核心链路）
    - 15% 概率查历史
    - 5%  概率提交反馈
    每次请求后模拟 1~3 秒思考时间（接近真实用户行为）
    """
    wait_time = between(1, 3)

    # 每个用户的状态
    user_seq: int = 0
    _counter = 0

    def on_start(self):
        """用户启动时分配唯一 ID 和初始 query 序号"""
        RecommendUser._counter += 1
        self.user_id = f"locust_user_{RecommendUser._counter}"
        self.query_idx = random.randint(0, len(RECOMMEND_PAYLOADS) - 1)
        self.last_recommendation_id = None
        self.last_restaurant_id = None

    @task(8)
    def recommend(self):
        """推荐接口 —— 核心压测目标"""
        global _llm_degraded_count, _llm_normal_count

        # 轮换使用不同 query，模拟真实多样性
        item = RECOMMEND_PAYLOADS[self.query_idx % len(RECOMMEND_PAYLOADS)]
        self.query_idx += 1

        payload = dict(item["payload"])
        payload["user_id"] = self.user_id

        with self.client.post(
            "/api/recommend",
            json=payload,
            name=f"POST /api/recommend [{item['name']}]",
            catch_response=True,
            timeout=90,
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    restaurants = data.get("recommendations", [])

                    # 判断 LLM 是否正常工作（有结果且包含解释字段视为正常）
                    if restaurants:
                        self.last_restaurant_id = restaurants[0].get("restaurant_id")
                        resp.success()
                        _llm_normal_count += 1
                    else:
                        # 返回 200 但空结果，可能是降级或无数据
                        resp.failure(f"空结果集 code={data.get('code')} msg={data.get('message','')}")
                        _llm_degraded_count += 1

                    # 保存 recommendation_id 供后续反馈使用
                    self.last_recommendation_id = data.get("recommendation_id")

                except json.JSONDecodeError:
                    resp.failure("响应非 JSON 格式")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def health_check(self):
        """健康检查 —— 验证服务存活"""
        with self.client.get(
            "/api/health",
            name="GET /api/health",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"健康检查失败: HTTP {resp.status_code}")

    @task(1)
    def get_history(self):
        """历史记录查询"""
        with self.client.get(
            f"/api/history?user_id={self.user_id}&page=1&page_size=10",
            name="GET /api/history",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def submit_feedback(self):
        """随机提交反馈（需要先有推荐结果，且必须有有效的 recommendation_id）"""
        # 必须同时持有 restaurant_id 和 recommendation_id 才提交
        # recommendation_id 为 None 时传 None（MySQL FK 对 NULL 不做检查）
        # 绝不传 "unknown" 之类的占位符，否则触发 FK constraint 失败
        if not self.last_restaurant_id or not self.last_recommendation_id:
            return

        payload = {
            "user_id": self.user_id,
            "restaurant_id": self.last_restaurant_id,
            "recommendation_id": self.last_recommendation_id,
            "rating": random.randint(1, 5),
            "chosen": random.choice([True, False]),
            "action_type": random.choice(FEEDBACK_ACTIONS),
        }

        with self.client.post(
            "/api/feedback",
            json=payload,
            name="POST /api/feedback",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


class HeavyRecommendUser(HttpUser):
    """
    高频推荐用户（模拟密集操作场景）：
    - 几乎只发推荐请求，思考时间极短
    - 用于测试推荐接口的极限承压能力
    """
    wait_time = between(2, 4)  # 降低高频用户的压力，避免 LLM 积压导致 HTTP 0
    weight = 1  # 占所有用户的 1/3（其余 2/3 是 RecommendUser）

    def on_start(self):
        HeavyRecommendUser._counter = getattr(HeavyRecommendUser, "_counter", 0) + 1
        self.user_id = f"heavy_user_{HeavyRecommendUser._counter}"
        self.query_idx = 0

    @task
    def recommend_fast(self):
        item = RECOMMEND_PAYLOADS[self.query_idx % len(RECOMMEND_PAYLOADS)]
        self.query_idx += 1
        payload = dict(item["payload"])
        payload["user_id"] = self.user_id

        with self.client.post(
            "/api/recommend",
            json=payload,
            name=f"POST /api/recommend [高频-{item['name']}]",
            catch_response=True,
            timeout=90,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")


# ── 自定义统计事件钩子 ────────────────────────────────────────────────────

@events.request.add_listener
def on_request(request_type, name, response_time, response_length,
               exception, context, **kwargs):
    """
    每次请求完成后的钩子：
    可在此累积自定义指标（如 LLM 超时率）
    """
    pass  # 如需自定义打点，在此扩展


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "=" * 60)
    print("  What-2-Eat Locust 压测启动")
    print("  Web UI: http://localhost:8089")
    print("  关注指标：RPS | P90/P99 延迟 | 失败率")
    print("=" * 60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时打印 LLM 降级统计"""
    total = _llm_normal_count + _llm_degraded_count
    if total > 0:
        rate = _llm_degraded_count / total * 100
        print(f"\n[LLM 统计] 正常: {_llm_normal_count} | 降级(空结果): {_llm_degraded_count} "
              f"| 降级率: {rate:.1f}%")
    print("=" * 60)
    print("  测试完成")
    print("  Statistics 页可查看 P50/P90/P99 详细数据")
    print("  Download Data → Download Report 导出 HTML 报告")
    print("=" * 60 + "\n")

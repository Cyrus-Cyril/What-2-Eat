"""
load_test.py
What-2-Eat 并发压力测试工具

功能：
  - 模拟多用户并发请求 /api/recommend 接口
  - 测试不同并发级别下的系统表现
  - 收集关键性能指标（QPS、延迟、错误率、LLM调用情况）
  - 生成可读的测试报告

使用方法：
  python load_test.py                    # 使用默认参数运行完整测试
  python load_test.py --quick            # 快速测试（3分钟内完成）
  python load_test.py --concurrent 50    # 固定50并发测试

输出：
  - 控制台实时进度
  - 压测结果摘要
  - 详细数据文件: load_test_results.json
"""

import asyncio
import argparse
import json
import time
import statistics
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path

try:
    import httpx
except ImportError:
    print("请先安装依赖: pip install httpx")
    exit(1)


# ── 配置常量 ──────────────────────────────────────────────

BASE_URL = "http://localhost:8000"
RECOMMEND_ENDPOINT = f"{BASE_URL}/api/recommend"
HEALTH_ENDPOINT = f"{BASE_URL}/api/health"

# 默认测试参数
DEFAULT_CONFIG = {
    "concurrent_users": [1, 5, 10, 20],      # 并发用户数列表
    "requests_per_user": 5,                   # 每个用户发送的请求数
    "ramp_up_time": 2,                        # 启动时间（秒），逐步增加并发
    "request_timeout": 90.0,                  # 单次请求超时时间（改为90s，适配LLM响应延迟）
}

# 测试用的推荐请求体（模拟真实场景）
TEST_REQUESTS = [
    {
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
    {
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
    {
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
    {
        "query": "适合两个人一起吃",
        "longitude": 114.35968,
        "latitude": 30.52878,
        "radius": 1000,
        "max_count": 6,
        "budget_min": 80,
        "budget_max": 150,
        "people_count": 2,
    },
    {
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
]


@dataclass
class RequestResult:
    """单次请求的结果记录"""
    user_id: int
    request_id: int
    start_time: float
    end_time: float
    duration_ms: float
    status_code: int
    success: bool
    error_message: str = ""
    response_size: int = 0


@dataclass
class TestScenario:
    """单个测试场景的配置和结果"""
    concurrent_users: int
    total_requests: int
    results: List[RequestResult] = field(default_factory=list)
    
    # 计算得出的指标
    total_duration: float = 0.0
    qps: float = 0.0
    avg_response_time: float = 0.0
    min_response_time: float = 0.0
    max_response_time: float = 0.0
    p50_response_time: float = 0.0
    p90_response_time: float = 0.0
    p99_response_time: float = 0.0
    error_rate: float = 0.0
    success_count: int = 0
    error_count: int = 0


class LoadTester:
    """
    并发压力测试器
    
    功能：
    - 异步发送HTTP请求
    - 控制并发数（使用Semaphore）
    - 收集详细指标
    - 生成统计报告
    """
    
    def __init__(self, base_url: str = BASE_URL, timeout: float = 30.0):
        self.base_url = base_url
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建HTTP客户端"""
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(timeout=self.timeout)
        return self.client
    
    async def health_check(self) -> bool:
        """检查服务是否可用"""
        try:
            client = await self._get_client()
            resp = await client.get(HEALTH_ENDPOINT)
            return resp.status_code == 200
        except Exception as e:
            print(f"[ERROR] 服务健康检查失败: {e}")
            return False
    
    async def send_recommend_request(
        self, 
        user_id: int, 
        request_id: int,
        payload: Dict[str, Any]
    ) -> RequestResult:
        """发送单次推荐请求"""
        result = RequestResult(
            user_id=user_id,
            request_id=request_id,
            start_time=time.time(),
            end_time=0,
            duration_ms=0,
            status_code=0,
            success=False,
        )
        
        try:
            client = await self._get_client()
            result.start_time = time.time()
            
            resp = await client.post(RECOMMEND_ENDPOINT, json=payload)
            
            result.end_time = time.time()
            result.duration_ms = (result.end_time - result.start_time) * 1000
            result.status_code = resp.status_code
            result.response_size = len(resp.content)
            result.success = (200 <= resp.status_code < 300)
            
            if not result.success:
                result.error_message = f"HTTP {resp.status_code}: {resp.text[:200]}"
                
        except httpx.TimeoutException:
            result.end_time = time.time()
            result.duration_ms = (result.end_time - result.start_time) * 1000
            result.error_message = "请求超时"
            
        except Exception as e:
            result.end_time = time.time()
            result.duration_ms = (result.end_time - result.start_time) * 1000
            result.error_message = str(e)[:200]
        
        return result
    
    async def simulate_user(
        self,
        user_id: int,
        num_requests: int,
        semaphore: asyncio.Semaphore,
        scenario: TestScenario
    ) -> None:
        """模拟单个用户的请求行为"""
        for i in range(num_requests):
            # 获取信号量许可（控制并发）
            async with semaphore:
                # 轮换使用不同的测试请求
                payload = TEST_REQUESTS[i % len(TEST_REQUESTS)]
                payload["user_id"] = f"test_user_{user_id}"
                
                # 发送请求并记录结果
                result = await self.send_recommend_request(user_id, i, payload)
                scenario.results.append(result)
    
    async def run_scenario(
        self,
        concurrent_users: int,
        requests_per_user: int,
        ramp_up_time: float = 2.0
    ) -> TestScenario:
        """
        运行单个测试场景
        
        参数:
            concurrent_users: 并发用户数
            requests_per_user: 每用户请求数
            ramp_up_time: 用户启动间隔（秒）
        
        返回:
            TestScenario 包含详细结果和统计指标
        """
        scenario = TestScenario(
            concurrent_users=concurrent_users,
            total_requests=concurrent_users * requests_per_user,
        )
        
        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(concurrent_users)
        
        print(f"\n{'='*60}")
        print(f"[START] 测试开始: {concurrent_users} 并发用户 x {requests_per_user} 请求/用户")
        print(f"   总请求数: {scenario.total_requests}")
        print(f"{'='*60}")
        
        # 记录开始时间
        start_time = time.time()
        
        # 创建所有用户任务
        tasks = []
        for user_id in range(concurrent_users):
            # 渐进式启动（避免瞬间冲击）
            if ramp_up_time > 0 and user_id > 0:
                delay = (ramp_up_time / concurrent_users) * user_id
                await asyncio.sleep(delay)
            
            task = asyncio.create_task(
                self.simulate_user(
                    user_id=user_id,
                    num_requests=requests_per_user,
                    semaphore=semaphore,
                    scenario=scenario,
                )
            )
            tasks.append(task)
        
        # 等待所有任务完成
        await asyncio.gather(*tasks)
        
        # 记录结束时间
        end_time = time.time()
        scenario.total_duration = end_time - start_time
        
        # 计算统计指标
        self._calculate_metrics(scenario)
        
        # 打印结果摘要
        self._print_scenario_summary(scenario)
        
        return scenario
    
    def _calculate_metrics(self, scenario: TestScenario) -> None:
        """计算测试场景的统计指标"""
        if not scenario.results:
            return
        
        # 基础计数
        scenario.success_count = sum(1 for r in scenario.results if r.success)
        scenario.error_count = len(scenario.results) - scenario.success_count
        scenario.error_rate = (scenario.error_count / len(scenario.results)) * 100
        
        # 只统计成功请求的响应时间
        success_durations = [r.duration_ms for r in scenario.results if r.success]
        
        if success_durations:
            scenario.avg_response_time = statistics.mean(success_durations)
            scenario.min_response_time = min(success_durations)
            scenario.max_response_time = max(success_durations)
            scenario.p50_response_time = self._percentile(success_durations, 50)
            scenario.p90_response_time = self._percentile(success_durations, 90)
            scenario.p99_response_time = self._percentile(success_durations, 99)
        
        # QPS计算
        if scenario.total_duration > 0:
            scenario.qps = len(scenario.results) / scenario.total_duration
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """计算百分位数"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (percentile / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])
    
    def _print_scenario_summary(self, scenario: TestScenario) -> None:
        """打印单个测试场景的摘要"""
        print(f"\n[RESULT] 测试结果:")
        print(f"   [TIME] 总耗时: {scenario.total_duration:.2f} 秒")
        print(f"   [QPS]  吞吐量: {scenario.qps:.2f} 请求/秒")
        print(f"   [OK]   成功:   {scenario.success_count}/{len(scenario.results)} ({100-scenario.error_rate:.1f}%)")
        print(f"   [FAIL] 失败:   {scenario.error_count}/{len(scenario.results)} ({scenario.error_rate:.1f}%)")
        
        if scenario.success_count > 0:
            print(f"\n   [LATENCY] 响应时间分布 (成功请求):")
            print(f"      平均值: {scenario.avg_response_time:.0f} ms")
            print(f"      最小值: {scenario.min_response_time:.0f} ms")
            print(f"      最大值: {scenario.max_response_time:.0f} ms")
            print(f"      P50:    {scenario.p50_response_time:.0f} ms")
            print(f"      P90:    {scenario.p90_response_time:.0f} ms")
            print(f"      P99:    {scenario.p99_response_time:.0f} ms")
        
        # 错误分析
        errors = [r for r in scenario.results if not r.success]
        if errors:
            print(f"\n   [WARN] 错误详情:")
            error_types = {}
            for err in errors:
                msg = err.error_message[:50] if err.error_message else "Unknown"
                error_types[msg] = error_types.get(msg, 0) + 1
            
            for msg, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"      [{count}次] {msg}")
    
    async def cleanup(self):
        """清理资源"""
        if self.client and not self.client.is_closed:
            await self.client.aclose()


async def run_full_test_suite(
    quick_mode: bool = False,
    fixed_concurrent: Optional[int] = None
) -> List[TestScenario]:
    """
    运行完整的测试套件
    
    参数:
        quick_mode: 快速模式（只测试1个并发级别）
        fixed_concurrent: 固定并发级别（如果指定则忽略其他参数）
    
    返回:
        所有测试场景的结果列表
    """
    tester = LoadTester(timeout=DEFAULT_CONFIG["request_timeout"])
    scenarios = []
    
    try:
        # 步骤1: 健康检查
        print("\n[CHECK] 正在检查服务状态...")
        if not await tester.health_check():
            print("[ERROR] 服务不可用！请确保后端服务已启动:")
            print("   cd backend && uvicorn app.main:app --reload")
            return scenarios
        print("[OK] 服务正常运行")
        
        # 确定测试配置
        if fixed_concurrent:
            concurrent_levels = [fixed_concurrent]
            requests_per_user = 10
        elif quick_mode:
            concurrent_levels = [5]
            requests_per_user = 3
        else:
            concurrent_levels = DEFAULT_CONFIG["concurrent_users"]
            requests_per_user = DEFAULT_CONFIG["requests_per_user"]
        
        print(f"\n[PLAN] 测试计划:")
        print(f"   并发级别: {concurrent_levels}")
        print(f"   请求数/用户: {requests_per_user}")
        
        # 步骤2: 逐个执行测试场景
        for i, concurrent in enumerate(concurrent_levels):
            print(f"\n\n[{i+1}/{len(concurrent_levels)}] 测试场景")
            
            scenario = await tester.run_scenario(
                concurrent_users=concurrent,
                requests_per_user=requests_per_user,
                ramp_up_time=min(2.0, concurrent * 0.1),  # 动态调整启动时间
            )
            scenarios.append(scenario)
            
            # 场景间休息，让系统恢复
            if i < len(concurrent_levels) - 1:
                print("\n[WAIT] 等待系统恢复...")
                await asyncio.sleep(3)
        
        # 步骤3: 生成总结报告
        print_final_report(scenarios)
        
        # 步骤4: 保存详细数据
        save_results_to_json(scenarios)
        
    finally:
        await tester.cleanup()
    
    return scenarios


def print_final_report(scenarios: List[TestScenario]) -> None:
    """打印最终汇总报告"""
    if not scenarios:
        return
    
    print("\n\n" + "="*70)
    print("[REPORT] 最终测试报告")
    print("="*70)
    
    print(f"\n{'并发用户':^8} | {'总请求':^8} | {'QPS':^8} | {'平均延迟':^10} | "
          f"{'P90':^8} | {'P99':^8} | {'错误率':^8}")
    print("-"*80)
    
    for s in scenarios:
        print(f"{s.concurrent_users:^8} | {len(s.results):^8} | {s.qps:^8.1f} | "
              f"{s.avg_response_time:^10.0f} | {s.p90_response_time:^8.0f} | "
              f"{s.p99_response_time:^8.0f} | {s.error_rate:^7.1f}%")
    
    # 性能瓶颈分析
    print("\n[ANALYSIS] 分析结论:")
    best_qps = max(scenarios, key=lambda s: s.qps)
    worst_latency = max(scenarios, key=lambda s: s.avg_response_time)
    
    print(f"   - 最佳吞吐量: {best_qps.concurrent_users} 并发时达到 {best_qps.qps:.1f} QPS")
    print(f"   - 最高延迟: {worst_latency.concurrent_users} 并发时平均 {worst_latency.avg_response_time:.0f}ms")
    
    # 判断系统瓶颈类型
    if any(s.error_rate > 10 for s in scenarios):
        print("   [WARN] 系统存在稳定性问题（错误率>10%）")
        print("   => 可能原因: LLM API限流、数据库连接池耗尽、内存不足")
    
    if scenarios[-1].avg_response_time > scenarios[0].avg_response_time * 3:
        print("   [WARN] 高并发下延迟急剧增加（>3倍）")
        print("   => 可能原因: 无并发控制、资源竞争严重、外部API成为瓶颈")
    
    if all(s.qps < 20 for s in scenarios):
        print("   [INFO] 吞吐量偏低（<20 QPS）")
        print("   => 优化建议: 引入LLM调用缓存、添加信号量限流、使用连接池")


def save_results_to_json(scenarios: List[TestScenario]) -> None:
    """保存详细测试结果到JSON文件"""
    output_file = Path(__file__).parent / "load_test_results.json"
    
    data = {
        "test_time": datetime.now().isoformat(),
        "summary": {
            "total_scenarios": len(scenarios),
            "total_requests": sum(len(s.results) for s in scenarios),
            "overall_success_rate": (
                sum(s.success_count for s in scenarios) /
                sum(len(s.results) for s in scenarios) * 100
                if scenarios else 0
            ),
        },
        "scenarios": []
    }
    
    for s in scenarios:
        scenario_data = asdict(s)
        # 将results转换为可序列化的格式
        scenario_data["results"] = [asdict(r) for r in s.results[:20]]  # 只保存前20条详情
        scenario_data["all_results_count"] = len(s.results)
        data["scenarios"].append(scenario_data)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n[SAVE] 详细数据已保存至: {output_file}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="What-2-Eat 并发压力测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python load_test.py              # 完整测试（约需5-10分钟）
  python load_test.py --quick      # 快速测试（约需1分钟）
  python load_test.py --concurrent 50  # 测试50并发
        """
    )
    
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="快速模式（仅测试5并发×3请求）"
    )
    
    parser.add_argument(
        "--concurrent", "-c",
        type=int,
        default=None,
        help="指定固定并发用户数（如: 10, 20, 50）"
    )
    
    parser.add_argument(
        "--requests", "-r",
        type=int,
        default=None,
        help="每个用户的请求数（默认: 5）"
    )
    
    args = parser.parse_args()
    
    print("="*60)
    print("     What-2-Eat 并发压力测试工具 v1.0")
    print("="*60)
    print(f"\n[TIME] 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[TARGET] 目标服务: {BASE_URL}")
    
    if args.requests:
        DEFAULT_CONFIG["requests_per_user"] = args.requests
    
    await run_full_test_suite(
        quick_mode=args.quick,
        fixed_concurrent=args.concurrent,
    )
    
    print(f"\n[DONE] 测试完成! 时间: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())

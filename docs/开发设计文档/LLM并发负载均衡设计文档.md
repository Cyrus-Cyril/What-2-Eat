# LLM 并发负载均衡设计文档

**模块**：`backend/app/services/llm_router.py` / `backend/app/services/explanation_builder.py` / `backend/app/services/intent_parser.py` / `backend/config.py`  
**编写日期**：2026-05-19  
**最后更新**：2026-05-20  
**状态**：已实现

---

## 1. 背景与需求

### 1.1 问题来源

What-2-Eat 在每次推荐请求中会触发多处 LLM 调用：

| 调用类型 | 所在模块 | 触发次数 |
|---------|---------|---------|
| 意图解析（intent parsing） | `intent_parser.py` | 每次推荐 ×1（结果有缓存） |
| 全局开场白 | `explanation_builder.py` | 每次推荐 ×1（结果有缓存） |
| 批量餐厅推荐话术 | `explanation_builder.py` | 每次推荐 ×1（单次调用替代 N 次） |

改造前，系统仅持有单个 `LLM_API_KEY`，直连阿里云 DashScope，无并发控制。qwen-turbo 单 Key 默认限制约 **5 QPS**，在 5–20 用户并发场景下极易触发 429 限流，导致意图解析和解释文案大量降级。

### 1.2 设计目标

- 支持 **5–20 用户并发**，LLM 调用不因限流而全部降级
- 改动最小，不引入外部中间件
- 保持已有的规则模板降级兜底机制不变
- 支持跨厂商多 Provider，单点故障自动切换
- 针对持续故障的槽位实现熔断，快速失败而非长期阻塞

---

## 2. 方案选型

经过评估，选择 **多 Key 轮询 + Semaphore 并发控制 + 熔断器** 的组合：

| 方案 | 说明 | 是否采用 |
|-----|------|---------|
| 多 Key 轮询 | 多个 API Key 轮流承接请求，分摊 QPS 配额 | ✅ 采用 |
| Semaphore + 队列 | `asyncio.Semaphore` 限制单 Key 并发上限，超限排队 | ✅ 采用 |
| 熔断器（Circuit Breaker） | 连续非限流 4xx 错误后暂停调用该槽位，冷却后自动恢复 | ✅ 采用 |
| 多 Provider 路由 | 配置多家 LLM 厂商，健康检查后路由 | 部分采用（支持跨厂商，无主动健康探测） |
| 共享路由器单例 | `intent_parser` 与 `explanation_builder` 共用同一路由实例 | ✅ 采用 |

### 并发容量计算

当前配置：2 个 Qwen Key + 6 个 DeepSeek Key，每个 Key 并发上限 3。

```
总并发上限 = 8 个槽位 × 3（每槽位 Semaphore）= 24 路同时进行的 LLM 调用
```

考虑每次推荐触发约 2 次 LLM 调用（意图解析 + 批量话术，开场白命中缓存时仅 1 次），可承载约 **12 个用户完全并发**。对于排队场景（请求在 Semaphore 前短暂等待）可支撑更高峰值。

---

## 3. 架构设计

### 3.1 模块关系

```
config.py          ──► LLM_PROVIDERS（槽位列表）
                              │
                              ▼
                    llm_router.py（LLMRouter 单例 router）
                         ▲          ▲
                         │          │
            intent_parser.py    explanation_builder.py
            （意图解析）         （开场白 + 批量话术）
```

`LLMRouter` 以模块级单例（`router`）形式存在，两处调用方共享同一路由实例和 Semaphore 池，避免槽位配额被重复独占。

### 3.2 槽位（Slot）模型

每个 `(url, key, model)` 三元组构成一个**槽位**，槽位是调度的最小单元：

```
LLM_PROVIDERS = [
    { url: DashScope, key: qwen-key-1,   model: qwen-max         },  # 槽位 0
    { url: DashScope, key: qwen-key-2,   model: qwen-max         },  # 槽位 1
    { url: DeepSeek,  key: ds-key-1,     model: deepseek-v4-flash },  # 槽位 2
    { url: DeepSeek,  key: ds-key-2,     model: deepseek-v4-flash },  # 槽位 3
    ...                                                               # 槽位 4–7（共 6 个 DeepSeek Key）
]
```

每个槽位持有独立的 `asyncio.Semaphore(3)`，保证单 Key 不超过并发上限。

### 3.3 路由流程（含熔断）

```
调用方（intent_parser / explanation_builder）
    │
    ├─ asyncio.wait_for(router.call(...), timeout=总超时)
    │
    ▼
LLMRouter.call(prompt, timeout, max_tokens, temperature)
    │
    ├─ 取当前轮询游标 start_idx（0→1→2→0→...）
    │
    ├─ 循环遍历所有槽位（最多 n 次）
    │      │
    │      ├─ _is_alive(idx)?
    │      │      ├─ 熔断中（dead_until 未到期）→ 跳过，继续下一槽位
    │      │      └─ 冷却结束 → 恢复可用，重置错误计数
    │      │
    │      ├─ 等待该槽位 Semaphore（最多 3 个并发，超限排队）
    │      │
    │      ├─ HTTP POST → LLM API（httpx，单次超时 = timeout 参数）
    │      │
    │      ├─ HTTP 200  → _record_success()，返回文本 ✓
    │      ├─ HTTP 429  → 释放 Semaphore，切换下一槽位
    │      ├─ HTTP 4xx  → _record_fatal_error()
    │      │               连续 3 次 → 熔断 120 秒，切换下一槽位
    │      ├─ 超时       → 释放 Semaphore，切换下一槽位
    │      └─ 其他异常  → 释放 Semaphore，切换下一槽位
    │
    └─ 所有槽位均失败 → 返回 None
                            │
                            ▼
                     调用方各自降级（见第 6 节）
```

### 3.4 超时层级

每次 LLM 调用存在两层超时保护，防止在 Semaphore 排队阶段无限阻塞：

| 层级 | 作用域 | 超时值 |
|-----|-------|-------|
| 内层：HTTP 请求超时 | 单次 httpx 请求 | 由调用方传入（见第 6 节） |
| 外层：总墙钟超时 | 含 Semaphore 排队 + 所有槽位轮询 | 由调用方用 `asyncio.wait_for` 包裹 |

### 3.5 Semaphore 懒初始化

`asyncio.Semaphore` 必须在事件循环启动后创建。模块在导入时事件循环可能尚未就绪，因此采用懒初始化策略：

```python
def _ensure_init(self) -> None:
    if self._semaphores is None:          # 首次 call() 时才创建
        self._semaphores = [asyncio.Semaphore(self._CONCURRENCY_PER_SLOT)
                            for _ in self._providers]
```

### 3.6 熔断器（Circuit Breaker）

针对持续返回非限流 4xx 错误（如鉴权失败、账户欠费）的槽位，避免每次请求都等待超时：

| 参数 | 值 | 说明 |
|-----|---|-----|
| `_CIRCUIT_BREAK_AFTER` | 3 | 连续非限流 4xx 次数达到此值触发熔断 |
| `_CIRCUIT_COOLDOWN` | 120 s | 熔断冷却时长，到期后自动尝试恢复 |

熔断期间该槽位被直接跳过（`_is_alive()` 返回 False），不消耗 Semaphore。冷却结束后下一次请求会自动尝试恢复，若成功则重置错误计数。

---

## 4. 关键实现

### 4.1 config.py — 多 Provider 解析

```python
def _parse_provider_slots(keys_env, url_env, model_env, url_default, model_default):
    """将逗号分隔的 Key 列表展开为多个槽位字典。"""
    keys = [k.strip() for k in os.getenv(keys_env, "").split(",") if k.strip()]
    if not keys:
        return []
    url = os.getenv(url_env, url_default)
    model = os.getenv(model_env, model_default)
    return [{"url": url, "key": k, "model": model} for k in keys]

LLM_PROVIDERS = (
    _parse_provider_slots("LLM_QWEN_KEYS",     "LLM_QWEN_API_URL",     "LLM_QWEN_MODEL",
                          "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo")
    + _parse_provider_slots("LLM_DEEPSEEK_KEYS", "LLM_DEEPSEEK_API_URL", "LLM_DEEPSEEK_MODEL",
                            "https://api.deepseek.com/v1", "deepseek-chat")
)

# 向后兼容：若新配置为空，回退到旧版单 Key
if not LLM_PROVIDERS and LLM_API_KEY:
    LLM_PROVIDERS = [{"url": LLM_API_URL, "key": LLM_API_KEY, "model": LLM_MODEL}]
```

### 4.2 llm_router.py — LLMRouter 核心（共享单例）

```python
class LLMRouter:
    _CONCURRENCY_PER_SLOT = 3      # 每个 Key 允许的最大并发调用数
    _CIRCUIT_BREAK_AFTER  = 3      # 连续非限流 4xx 达到此值触发熔断
    _CIRCUIT_COOLDOWN     = 120.0  # 熔断冷却时长（秒）

    async def call(
        self, prompt: str, timeout: float = 15.0,
        max_tokens: int = 120, temperature: float = 0.7,
    ) -> str | None:
        self._ensure_init()
        n = len(self._providers)
        start = self._next_start_idx()            # 轮询游标推进

        for i in range(n):
            idx = (start + i) % n
            if not self._is_alive(idx):           # 熔断检查
                continue
            async with self._semaphores[idx]:     # 并发限流，超限时排队等待
                try:
                    resp = await http_post(self._providers[idx], prompt, timeout)
                    if resp.status_code == 429:
                        continue                  # 限流 → 切换槽位
                    if 400 <= resp.status_code < 500:
                        self._record_fatal_error(idx, resp.status_code)
                        continue                  # 非限流 4xx → 熔断计数，切换槽位
                    self._record_success(idx)
                    return parse_content(resp)    # 成功 ✓
                except (TimeoutException, Exception):
                    continue                      # 超时/网络异常 → 切换槽位

        return None                               # 全部失败 → 交由调用方降级

# 模块级单例，intent_parser 与 explanation_builder 共享
router = LLMRouter(config.LLM_PROVIDERS)
```

### 4.3 intent_parser.py — 意图解析调用

```python
# 两层超时：内层 HTTP 20s，外层总墙钟 25s（含 Semaphore 排队）
content = await asyncio.wait_for(
    _llm_router.call(prompt, timeout=20.0, max_tokens=400, temperature=0),
    timeout=25.0,
)
```

**失败缓存（Fail Cache）**：LLM 不可用时写入空结果，TTL 60 秒。60 秒内后续相同 query 直接返回空字典（降级），不再重试 LLM，防止串行雪崩。成功结果写入持久缓存，无 TTL，最多保留 200 条。

**per-query 锁（Thundering Herd 防护）**：相同 query 并发到达时，只有第一个请求调用 LLM，其余等待锁释放后命中缓存，避免 N 个并发对同一 query 发起 N 次 LLM 调用。

### 4.4 explanation_builder.py — 解释系统调用

```python
async def _call_llm(prompt, timeout=3.0, total_timeout=None, max_tokens=120):
    """
    total_timeout 默认 = timeout + 5s，给 Semaphore 排队预留缓冲。
    超出 total_timeout 时直接降级，不再等待。
    """
    wall_clock = total_timeout if total_timeout is not None else (timeout + 5.0)
    try:
        return await asyncio.wait_for(
            _router.call(prompt, timeout=timeout, max_tokens=max_tokens),
            timeout=wall_clock,
        )
    except asyncio.TimeoutError:
        logger.warning("LLM 调用总超时（含排队 %.1fs），降级为规则模板", wall_clock)
        return None
```

各调用点超时参数：

| 调用场景 | HTTP 超时 | 总墙钟超时 | 降级策略 |
|---------|---------|---------|---------|
| 开场白 `build_explanation_system` | 3.0 s | 8.0 s | 4 档规则模板（neutral/preferred/required/fallback） |
| 单餐厅话术 `build_ai_speech` | 2.0 s | 7.0 s | 返回 `None`，前端不展示 ai_speech |
| 批量话术 `build_ai_speeches_for_top_n` | 4.0 s | 10.0 s | 全部返回 `None` |

**批量调用优化**：`build_ai_speeches_for_top_n` 将 N 家餐厅打包为一次 LLM 调用，`max_count=6` 时从原来的 6 次并发调用降至 1 次，大幅降低高并发下的 LLM 请求数。

**开场白缓存**：相同意图模式 + 核心标签 + 反馈摘要组合复用 LLM 结果（`_hello_cache`，LRU 上限 100 条），避免相同场景重复调用。

---

## 5. 配置说明

### 5.1 .env 配置格式

```env
# Qwen / DashScope（同一账号下创建多个 API Key，在阿里云百炼控制台申请）
LLM_QWEN_KEYS=sk-key1,sk-key2
LLM_QWEN_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_QWEN_MODEL=qwen-max

# DeepSeek
LLM_DEEPSEEK_KEYS=sk-key3,sk-key4,sk-key5,sk-key6,sk-key7,sk-key8
LLM_DEEPSEEK_API_URL=https://api.deepseek.com
LLM_DEEPSEEK_MODEL=deepseek-v4-flash
```

### 5.2 扩展并发容量

增加并发上限有两种方式：

**方式 A：增加 Key 数量（推荐）**

在 `.env` 的逗号列表中追加新 Key，无需修改代码：
```env
LLM_QWEN_KEYS=sk-key1,sk-key2,sk-key3,sk-key4
```
每增加 1 个 Key，并发上限 +3。

**方式 B：调整每槽位并发数**

修改 `llm_router.py` 中的常量（需确认 API 账户实际限制）：
```python
_CONCURRENCY_PER_SLOT = 5  # 从 3 调整为 5
```

### 5.3 向后兼容

若 `.env` 中未配置新格式的 Key，系统自动回退到旧版 `LLM_API_KEY` 单 Key 模式，不影响已有部署。

---

## 6. 错误处理与降级

### 6.1 路由器层降级

| 情况 | 路由器行为 | 说明 |
|-----|-----------|-----|
| 单个槽位 429 限流 | 切换下一槽位 | 对调用方透明 |
| 单个槽位 HTTP 超时 | 切换下一槽位 | 对调用方透明 |
| 单个槽位非限流 4xx | 熔断计数 +1，切换下一槽位 | 连续 3 次后熔断 120 秒 |
| 槽位熔断中 | 直接跳过，不等待 | 快速失败，不阻塞后续槽位 |
| 所有槽位均失败 | 返回 `None` | 触发调用方降级 |
| 未配置任何 Key | 立即返回 `None` | 触发调用方降级 |

### 6.2 调用方降级策略

**intent_parser.py**：
- LLM 超时/不可用 → 返回全 `neutral` 等权默认约束（`_default_neutral_constraint()`），推荐系统继续以综合评分模式运行
- 写入失败缓存（TTL 60 s），60 秒内同 query 不重试 LLM

**explanation_builder.py**：
- 开场白失败 → 按意图强度选择 4 档预置规则模板文案
- 单餐厅话术失败 → 返回 `None`，前端不展示 ai_speech 字段
- 批量话术失败 → 全部返回 `None`

### 6.3 最差情况等待时长

设 N = provider 槽位数，各场景在**所有槽位均超时**时的最长等待：

| 调用场景 | 外层总超时 | 单槽 HTTP 超时 | 最终降级时间 |
|---------|---------|-------------|------------|
| 意图解析 | 25 s | 20 s | ≤ 25 s |
| 开场白 | 8 s | 3 s | ≤ 8 s |
| 批量话术 | 10 s | 4 s | ≤ 10 s |

外层 `asyncio.wait_for` 总超时是硬上限，无论槽位数量多少，超时即降级。

---

## 7. 涉及文件清单

| 文件 | 说明 |
|-----|------|
| `backend/config.py` | `_parse_provider_slots()`、`LLM_PROVIDERS`；保留旧版变量向后兼容 |
| `backend/app/services/llm_router.py` | `LLMRouter` 类（轮询 + Semaphore + 熔断器）；模块级单例 `router` |
| `backend/app/services/intent_parser.py` | 使用共享 `router`；双层超时（20 s / 25 s）；失败缓存 TTL 60 s；per-query 锁 |
| `backend/app/services/explanation_builder.py` | 使用共享 `router`；`_call_llm` 封装总墙钟超时；批量话术单次调用优化；开场白 LRU 缓存 |
| `backend/.env` | `LLM_QWEN_KEYS`、`LLM_DEEPSEEK_KEYS` 等配置项（不入版本库） |

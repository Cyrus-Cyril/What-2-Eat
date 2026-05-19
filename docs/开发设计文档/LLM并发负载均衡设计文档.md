# LLM 并发负载均衡设计文档

**模块**：`backend/app/services/explanation_builder.py` / `backend/config.py`  
**编写日期**：2026-05-19  
**状态**：已实现

---

## 1. 背景与需求

### 1.1 问题来源

What-2-Eat 的解释系统（`explanation_builder.py`）在每次推荐请求中会触发 LLM 调用：

| 调用类型 | 函数 | 超时 | 触发次数 |
|---------|------|------|---------|
| 全局开场白 | `build_explanation_system` | 3.0 s | 每次推荐 ×1 |
| 单餐厅推荐话术 | `build_ai_speech` | 2.0 s | 每次推荐 × 返回餐厅数 |

改造前，系统仅持有单个 `LLM_API_KEY`，直连阿里云 DashScope，无并发控制。qwen-turbo 单 Key 默认限制约 **5 QPS**，在 5–20 用户并发场景下极易触发 429 限流，导致解释文案大量降级为规则模板。

### 1.2 设计目标

- 支持 **5–20 用户并发**，LLM 调用不因限流而全部降级
- 改动最小，不引入外部中间件
- 保持已有的规则模板降级兜底机制不变
- 支持跨厂商多 Provider，单点故障自动切换

---

## 2. 方案选型

经过评估，选择 **方案二（Semaphore 并发控制）+ 方案一（多 Key 轮询）** 的组合：

| 方案 | 说明 | 是否采用 |
|-----|------|---------|
| 方案一：多 Key 轮询 | 多个 API Key 轮流承接请求，分摊 QPS 配额 | ✅ 采用 |
| 方案二：Semaphore + 队列 | `asyncio.Semaphore` 限制单 Key 并发上限，超限排队 | ✅ 采用 |
| 方案三：多 Provider 路由 | 配置多家 LLM 厂商，健康检查后路由 | 部分采用（支持跨厂商，无健康探测） |

### 并发容量计算

当前配置：2 个 Qwen Key + 1 个 DeepSeek Key，每个 Key 并发上限 5。

```
总并发上限 = 3 个槽位 × 5（每槽位 Semaphore）= 15 路同时进行的 LLM 调用
```

考虑每次推荐触发约 2–4 次 LLM 调用，可承载约 **5–7 个用户完全并发**，对于排队场景（请求在 Semaphore 前短暂等待）可支撑更高峰值。

---

## 3. 架构设计

### 3.1 槽位（Slot）模型

每个 `(url, key, model)` 三元组构成一个**槽位**，槽位是调度的最小单元：

```
LLM_PROVIDERS = [
    { url: DashScope, key: qwen-key-1, model: qwen-turbo  },   # 槽位 0
    { url: DashScope, key: qwen-key-2, model: qwen-turbo  },   # 槽位 1
    { url: DeepSeek,  key: ds-key-1,   model: deepseek-chat }, # 槽位 2
]
```

每个槽位持有独立的 `asyncio.Semaphore(5)`，保证单个 Key 不超过 API 限制。

### 3.2 路由流程

```
_call_llm(prompt)
    │
    ▼
_LLMRouter.call(prompt)
    │
    ├─ 取当前轮询游标 start_idx（0→1→2→0→...）
    │
    ├─ 尝试槽位 start_idx
    │      ├─ 等待该槽位 Semaphore（最多5个并发）
    │      ├─ HTTP POST → LLM API
    │      ├─ 成功 → 返回文本 ✓
    │      ├─ 429  → 释放 Semaphore，切换下一槽位
    │      ├─ 超时 → 释放 Semaphore，切换下一槽位
    │      └─ 异常 → 释放 Semaphore，切换下一槽位
    │
    ├─ 尝试槽位 (start_idx+1) % n ...
    │
    └─ 所有槽位失败 → 返回 None
                          │
                          ▼
                   调用方降级为规则模板（原有逻辑，不变）
```

### 3.3 Semaphore 懒初始化

`asyncio.Semaphore` 必须在事件循环启动后创建。模块在导入时（`import explanation_builder`）事件循环可能尚未就绪，因此采用懒初始化策略：

```python
def _ensure_init(self) -> None:
    if self._semaphores is None:          # 首次 call() 时才创建
        self._semaphores = [asyncio.Semaphore(5) for _ in self._providers]
```

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

### 4.2 explanation_builder.py — _LLMRouter 核心

```python
class _LLMRouter:
    _CONCURRENCY_PER_SLOT = 5

    async def call(self, prompt: str, timeout: float = 3.0) -> str | None:
        self._ensure_init()
        n = len(self._providers)
        start = self._next_start_idx()        # 轮询游标推进

        for i in range(n):
            idx = (start + i) % n
            async with self._semaphores[idx]: # 并发限流，超限时排队等待
                try:
                    resp = await http_post(self._providers[idx], prompt, timeout)
                    if resp.status_code == 429:
                        continue              # 限流 → 切换槽位
                    return parse_content(resp)
                except (TimeoutException, Exception):
                    continue                  # 失败 → 切换槽位

        return None                           # 全部失败 → 交由调用方降级
```

---

## 5. 配置说明

### 5.1 .env 配置格式

```env
# Qwen / DashScope（同一账号下创建多个 API Key，在阿里云百炼控制台申请）
LLM_QWEN_KEYS=sk-key1,sk-key2
LLM_QWEN_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_QWEN_MODEL=qwen-turbo

# DeepSeek
LLM_DEEPSEEK_KEYS=sk-key3
LLM_DEEPSEEK_API_URL=https://api.deepseek.com/v1
LLM_DEEPSEEK_MODEL=deepseek-chat
```

### 5.2 扩展并发容量

增加并发上限有两种方式：

**方式 A：增加 Key 数量（推荐）**

在 `.env` 的逗号列表中追加新 Key，无需修改代码：
```env
LLM_QWEN_KEYS=sk-key1,sk-key2,sk-key3,sk-key4
```
每增加 1 个 Key，并发上限 +5。

**方式 B：调整每槽位并发数**

修改 `explanation_builder.py` 中的常量（需确认 API 账户实际限制）：
```python
_CONCURRENCY_PER_SLOT = 8  # 从 5 调整为 8
```

### 5.3 向后兼容

若 `.env` 中未配置新格式的 Key，系统自动回退到旧版 `LLM_API_KEY` 单 Key 模式，不影响已有部署。

---

## 6. 错误处理与降级

| 情况 | 路由器行为 | 最终用户表现 |
|-----|-----------|-------------|
| 单个槽位 429 限流 | 释放 Semaphore，切换下一槽位 | 透明，无感知 |
| 单个槽位超时 | 释放 Semaphore，切换下一槽位 | 透明，无感知 |
| 所有槽位均失败 | 返回 `None` | 使用规则模板文案（已有兜底） |
| `.env` 未配置任何 Key | `LLM_PROVIDERS` 为空，`call()` 立即返回 `None` | 使用规则模板文案 |

---

## 7. 涉及文件清单

| 文件 | 改动说明 |
|-----|---------|
| `backend/config.py` | 新增 `_parse_provider_slots()`、`LLM_PROVIDERS`；保留旧版变量向后兼容 |
| `backend/app/services/explanation_builder.py` | 新增 `_LLMRouter` 类；`_call_llm()` 改为委托 `_router.call()` |
| `backend/.env` | 新增 `LLM_QWEN_KEYS`、`LLM_DEEPSEEK_KEYS` 等配置项（不入版本库） |

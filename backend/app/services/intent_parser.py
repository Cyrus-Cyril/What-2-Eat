"""
app/services/intent_parser.py
自然语言意图解析 —— 调用 LLM 产出动态约束集（IntentConstraint），多源合并为 RecommendRequest
三层解析架构：维度（Dimension）+ 目标值（Value）+ 强度（Strength）+ 权重（Weight）
  strength="required"  — 用户使用绝对词（"必须、一定要、只能、不要"）→ 陡峭 S 型惩罚
  strength="preferred" — 用户使用建议词（"想吃、喜欢、稍微、最好是"）→ 平缓指数衰减
  strength="neutral"   — 用户未提及，系统自动补全                     → 无惩罚
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time as _time
from dataclasses import dataclass, field
from typing import Any

import config
from app.models.schemas import RecommendRequest
from app.services.user_profile import get_user_profile
from app.services.llm_router import router as _llm_router

# ── Redis 客户端（可选，不安装或未配置时为 None）
try:
    from app.db.redis_client import redis_client as _redis_client
except Exception:
    _redis_client = None

_REDIS_TTL = 3600  # 意图缓存有效期（1h）

# ── 意图解析结果内存缓存（query → unified dict）───────────────────────
# 用于避免相同 query 重复调用 LLM，最多缓存 200 条
# 同时用 Lock 防止相同 query 并发触发多次 LLM 调用（thundering herd）
_MAX_CACHE_SIZE = 200
_intent_cache: dict[str, dict] = {}
_intent_locks: dict[str, asyncio.Lock] = {}  # per-query 锁
# 失败缓存过期时间： cache_key → monotonic 时间戳（过期后被视为 miss，重新尝试 LLM）
_intent_cache_ttl: dict[str, float] = {}
_FAIL_CACHE_TTL = 60.0  # 失败缓存有效期（秒）：LLM 超时/不可用时，60s 内后续请求直接降级，不再重试

logger = logging.getLogger(__name__)

# ── 面向 Redis 的异步辅助函数 (同步客户端包装为线程池调用) ──────────
async def _redis_get(key: str) -> str | None:
    """non-blocking Redis GET（内部用）"""
    if not _redis_client:
        return None
    try:
        return await asyncio.to_thread(_redis_client.get, key)
    except Exception:
        return None


async def _redis_setex(key: str, ttl: int, value: str) -> None:
    """non-blocking Redis SETEX（内部用）"""
    if not _redis_client:
        return
    try:
        await asyncio.to_thread(_redis_client.setex, key, ttl, value)
    except Exception:
        pass


# ── 查询归一化：将不同写法的同义 query 映射到同一 key ───────────────
def _normalize_query(q: str) -> str:
    """query 标准化：去标点、小写、去语气词"""
    q = q.strip().lower()
    q = re.sub(r'[，。！？,!?~～\s]+', '', q)
    q = re.sub(r'(我想|我要|帮我|给我|随便|一下|一点|有点|有些)', '', q)
    return q


def _semantic_key(result: dict) -> str:
    """LLM 结果 → 语义结构 Redis key（不同写法同意图的请求共享）"""
    tags = sorted(result.get("taste", []) or [])
    price = result.get("budget_max")
    radius = result.get("radius")
    return f"intent:sem:{','.join(tags)}:{price}:{radius}"

# ── 默认权重（各维度等权基准）────────────────────────────────────────
_DEFAULT_WEIGHTS: dict[str, float] = {
    "distance": 0.30,
    "price":    0.25,
    "rating":   0.25,
    "tags":     0.20,
}


@dataclass
class ConstraintItem:
    """单维度约束描述"""
    values: list[str] = field(default_factory=list)   # 标签值列表（tags 维度）
    preferred: float | None = None                     # 期望值（price 维度，元）
    max_limit: float | None = None                     # 硬性上限（price/distance）
    strength: str = "neutral"                          # required / preferred / neutral
    weight: float = 0.25                               # LLM 分配的维度权重 0~1
    tolerance: str | None = None                       # high/medium/low（price 专用）


@dataclass
class IntentConstraint:
    """
    analyze_intent() 的输出 —— 动态约束集。
    驱动 recommender 的惩罚计算与动态权重融合。

    constraints: 各维度约束（tags/price/distance/rating）
    exclude_tags: 用户明确排斥的标签（直接硬过滤）
    reason_hint:  LLM 一句话总结用户意图（供解释系统使用）
    fallback_applied: True 表示 required 已被降级为 preferred（兜底触发后）
    """
    intent_type: str = "adaptive_constraint"
    constraints: dict[str, ConstraintItem] = field(default_factory=dict)
    exclude_tags: list[str] = field(default_factory=list)
    reason_hint: str = ""
    fallback_applied: bool = False


# ── 统一 LLM Prompt（一次调用同时提取参数 + 约束集）────────────────
_UNIFIED_PROMPT = """\
你是一个餐饮意图解析助手。请从用户输入中同时提取结构化参数与约束集，以标准 JSON 格式输出。

**Part A — 基础参数**：
- `budget_max`：最高价格（数字，"很贵"设200，"便宜"设30，否则 null）
- `budget_min`：最低价格（数字，否则 null）
- `radius`：搜索范围（数字，单位米。"附近"设1000，"很近"设500，"远一点"设3000，否则 null）
- `taste`：口味或菜系关键词数组（如 ["川菜","火锅"]，否则 []）
- `scene`：就餐场景（如 "聚餐"/"约会"，否则 null）

**Part B — 约束集**（键为维度 tags/price/distance/rating）：
- `strength`：
  - "required"  → 用户使用了"必须、一定要、只能、不要"等绝对词
  - "preferred" → 用户使用了"想吃、喜欢、稍微、最好是"等建议词
  - "neutral"   → 用户未提及
- `weight`：根据用户说话重心分配 0~1（各维度之和应为 1.0）
- `values`：（仅 tags 维度）菜系/口味标签数组
- `preferred`：（仅 price 维度）期望价格（数字，元）
- `max_limit`：硬性上限（price/distance，数字；price 单位元，distance 单位米）
- `tolerance`：（仅 price 维度）"high"/"medium"/"low"，对超价的容忍度

**Part C — 其他**：
- `exclude_tags`：用户明确说"不要/不喜欢"的标签数组（否则 []）
- `reason_hint`：一句话总结用户意图（中文）

用户输入："{query}"

输出要求：只输出 JSON，严禁任何额外解释。
示例：{{"budget_max": 100, "budget_min": null, "radius": null, "taste": ["火锅"], "scene": null, \
"constraints": {{"tags": {{"values": ["火锅"], "strength": "required", "weight": 0.5}}, \
"price": {{"preferred": 80, "max_limit": 100, "strength": "preferred", "weight": 0.3, "tolerance": "high"}}, \
"distance": {{"max_limit": 2000, "strength": "neutral", "weight": 0.2}}}}, \
"exclude_tags": [], "reason_hint": "用户想吃火锅，预算约百元"}}\
"""


class IntentParser:
    DEFAULT_VALUES: dict[str, Any] = {
        "longitude": 114.362,   # 默认光谷
        "latitude": 30.532,
        "radius": 2000,
        "budget_min": 0,
        "budget_max": 100,
        "taste": [],
        "max_count": None,
    }

    async def analyze_intent(
        self,
        user_input: str | None,
        context: dict | None = None,
    ) -> IntentConstraint:
        """
        分析用户意图，返回 IntentConstraint（动态约束集）。
        - 有输入 → 调用 LLM 提取约束（strength/weight/values/max_limit）
        - 无输入 → 返回全 neutral 等权默认约束
        """
        if not user_input or not user_input.strip():
            return self._default_neutral_constraint()

        raw = await self._call_unified_llm(user_input)
        if not raw:
            return self._default_neutral_constraint()
        return self._parse_constraint(raw)

    def relax_to_preferred(self, constraint: IntentConstraint) -> IntentConstraint:
        """
        将所有 required 约束降级为 preferred，供兜底（Fallback）使用。
        当 Top-N 全部分数过低时触发，保证推荐系统有可用结果输出。
        """
        for item in constraint.constraints.values():
            if item.strength == "required":
                item.strength = "preferred"
        constraint.fallback_applied = True
        logger.info(
            "兜底降级：所有 required 约束已降级为 preferred，reason_hint=%s",
            constraint.reason_hint,
        )
        return constraint

    @staticmethod
    def _default_neutral_constraint() -> IntentConstraint:
        """无输入时返回全 neutral 等权默认约束"""
        w = _DEFAULT_WEIGHTS
        return IntentConstraint(
            constraints={
                "distance": ConstraintItem(strength="neutral", weight=w["distance"]),
                "price":    ConstraintItem(strength="neutral", weight=w["price"]),
                "rating":   ConstraintItem(strength="neutral", weight=w["rating"]),
                "tags":     ConstraintItem(strength="neutral", weight=w["tags"]),
            },
            reason_hint="用户未提供明确偏好，按综合评分推荐",
        )

    @staticmethod
    def _parse_constraint(raw: dict) -> IntentConstraint:
        """
        将 LLM 返回的 dict 解析为 IntentConstraint，并补齐/归一化权重
        """
        constraints: dict[str, ConstraintItem] = {}
        raw_c = raw.get("constraints") or {}

        for dim, val in raw_c.items():
            if not isinstance(val, dict):
                continue
            strength = val.get("strength", "neutral")
            if strength not in ("required", "preferred", "neutral"):
                strength = "neutral"
            constraints[dim] = ConstraintItem(
                values=val.get("values", []) if isinstance(val.get("values"), list) else [],
                preferred=float(val["preferred"]) if val.get("preferred") is not None else None,
                max_limit=float(val["max_limit"]) if val.get("max_limit") is not None else None,
                strength=strength,
                weight=float(val.get("weight") or 0.25),
                tolerance=val.get("tolerance"),
            )

        # 补齐缺失维度（neutral，平分剩余权重）
        all_dims = ["tags", "price", "distance", "rating"]
        existing_weight = sum(c.weight for c in constraints.values())
        missing = [d for d in all_dims if d not in constraints]
        if missing:
            per = max(0.0, round((1.0 - existing_weight) / len(missing), 4))
            # 对于没有分配权重的维度，默认分配剩余权重的平均值，并设置为 neutral
            for d in missing:
                constraints[d] = ConstraintItem(
                    strength="neutral",
                    weight=per,
                )

        # 归一化：确保权重之和为 1.0
        total_w = sum(c.weight for c in constraints.values()) or 1.0
        for c in constraints.values():
            c.weight = round(c.weight / total_w, 4)

        # 解析 exclude_tags（用户明确排斥的标签）
        exclude = raw.get("exclude_tags", [])
        return IntentConstraint(
            constraints=constraints,
            exclude_tags=exclude if isinstance(exclude, list) else [],
            reason_hint=raw.get("reason_hint", ""),
        )

    async def _call_unified_llm(self, user_input: str) -> dict:
        """
        调用 LLM 一次，同时提取基础参数（budget/radius/taste）和约束集（IntentConstraint）。
        查询顺序：L1 进程内字典 → L2a Redis（归一化精确 key）→ LLM。
        失败时返回空字典，上层各自降级为默认值。
        """
        cache_key = _normalize_query(user_input)  # L1 / L2a 缓存键（归一化后）

        # ── L1: 进程内字典（最快，检查 TTL）────────────────────────────
        if cache_key in _intent_cache:
            ttl = _intent_cache_ttl.get(cache_key, 0.0)
            if ttl == 0.0 or _time.monotonic() < ttl:
                logger.debug("意图解析缓存命中 (L1): %s", cache_key[:30])
                return _intent_cache[cache_key]
            del _intent_cache[cache_key]
            del _intent_cache_ttl[cache_key]

        # ── L2a: Redis 归一化精确 key──────────────────────────────────
        redis_l2a_key = f"intent:{hashlib.md5(cache_key.encode()).hexdigest()}"
        cached_json = await _redis_get(redis_l2a_key)
        if cached_json:
            try:
                result = json.loads(cached_json)
                logger.debug("意图解析缓存命中 (L2a Redis): %s", cache_key[:30])
                _intent_cache[cache_key] = result  # 回填 L1
                return result
            except Exception:
                pass

        if not _llm_router.has_providers:
            logger.debug("LLM 未配置，跳过意图解析")
            return {}

        # ── per-query 锁：同一 query 并发时只发起一次 LLM 调用 ──────────
        if cache_key not in _intent_locks:
            _intent_locks[cache_key] = asyncio.Lock()
        lock = _intent_locks[cache_key]

        async with lock:
            # 锁内再检查一次 L1（可能已被前一个请求填充）
            if cache_key in _intent_cache:
                ttl = _intent_cache_ttl.get(cache_key, 0.0)
                if ttl == 0.0 or _time.monotonic() < ttl:
                    logger.debug("意图解析缓存命中（锁内）: %s", cache_key[:30])
                    return _intent_cache[cache_key]
                del _intent_cache[cache_key]
                del _intent_cache_ttl[cache_key]

            prompt = _UNIFIED_PROMPT.format(query=user_input)
            try:
                content = await asyncio.wait_for(
                    _llm_router.call(prompt, timeout=3.5, max_tokens=400, temperature=0),
                    timeout=4.0,
                )
            except asyncio.TimeoutError:
                logger.warning("意图解析 LLM 调用超时（4s），降级为默认值，写入短期 TTL 缓存")
                _intent_cache[cache_key] = {}
                _intent_cache_ttl[cache_key] = _time.monotonic() + _FAIL_CACHE_TTL
                return {}

            if not content:
                logger.warning("LLM 所有槽位不可用，意图解析降级为默认值，写入短期 TTL 缓存")
                _intent_cache[cache_key] = {}
                _intent_cache_ttl[cache_key] = _time.monotonic() + _FAIL_CACHE_TTL
                return {}

            try:
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                result = json.loads(content)
                logger.debug("LLM 统一解析响应: %s", content[:200])

                # LRU 清理
                if len(_intent_cache) >= _MAX_CACHE_SIZE:
                    keys_to_remove = list(_intent_cache.keys())[:_MAX_CACHE_SIZE // 2]
                    for k in keys_to_remove:
                        del _intent_cache[k]
                        _intent_locks.pop(k, None)
                        _intent_cache_ttl.pop(k, None)

                # 写入 L1 进程内字典
                _intent_cache[cache_key] = result
                _intent_cache_ttl.pop(cache_key, None)

                # 写入 L2a Redis（归一化精确 key）
                result_json = json.dumps(result, ensure_ascii=False)
                await _redis_setex(redis_l2a_key, _REDIS_TTL, result_json)

                # 写入 L2b Redis（语义结构 key，同意图不同写法共享）
                sem_key = _semantic_key(result)
                await _redis_setex(sem_key, _REDIS_TTL, result_json)
                logger.debug("意图解析写入 Redis L2a=%s L2b=%s", redis_l2a_key, sem_key)

                return result
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.warning("LLM 响应解析失败: %s", e)
        return {}

    async def parse(
        self,
        user_id: str | None,
        query: str | None,
        raw_params: dict,
    ) -> RecommendRequest:
        """
        多源参数合并：Query(LLM 单次) > Raw Params > History > Default
        LLM 调用只发生一次（_call_unified_llm），同时产出基础参数与 IntentConstraint。
        IntentConstraint 存入 req.intent，供 recommend_async 直接使用（不再重复调用 LLM）。
        """
        # Step 1: 单次 LLM 调用 —— 同时提取基础参数和约束集
        unified: dict = {}
        if query and query.strip():
            unified = await self._call_unified_llm(query)

        # Step 2: 从统一结果中解析 IntentConstraint
        intent = self._parse_constraint(unified) if unified else self._default_neutral_constraint()

        # Step 3: 获取历史偏好（有 user_id 时才查询）
        history_profile: dict = {}
        if user_id:
            history_profile = await get_user_profile(user_id)

        # Step 4: 合并参数
        final: dict[str, Any] = {}

        # 经纬度：前端传值 > 历史 > 默认
        final["longitude"] = (
            raw_params.get("longitude")
            or (history_profile.get("last_location") or {}).get("lng")
            or self.DEFAULT_VALUES["longitude"]
        )
        final["latitude"] = (
            raw_params.get("latitude")
            or (history_profile.get("last_location") or {}).get("lat")
            or self.DEFAULT_VALUES["latitude"]
        )

        # 预算/范围：LLM > 前端 > 历史 > 默认
        for key in ["budget_min", "budget_max", "radius"]:
            final[key] = (
                unified.get(key)
                or raw_params.get(key)
                or history_profile.get(f"avg_{key}")
                or self.DEFAULT_VALUES.get(key)
            )

        # 口味：LLM + 前端 的并集；都无时用历史
        taste_set: set[str] = set()
        llm_taste = unified.get("taste", [])
        if isinstance(llm_taste, list):
            taste_set.update(llm_taste)
        elif isinstance(llm_taste, str) and llm_taste:
            taste_set.add(llm_taste)

        rp_taste = raw_params.get("taste")
        if rp_taste:
            if isinstance(rp_taste, list):
                taste_set.update(rp_taste)
            else:
                taste_set.add(str(rp_taste))

        if not taste_set:
            taste_set.update(history_profile.get("preferred_tastes", []))

        final["taste"] = ",".join(taste_set) if taste_set else None

        # max_count：前端传值 > 默认
        final["max_count"] = raw_params.get("max_count") or self.DEFAULT_VALUES["max_count"]
        final["max_distance"] = raw_params.get("max_distance")
        final["query"] = query

        req = RecommendRequest(user_id=user_id, **final)
        req.intent = intent   # 注入约束集，recommend_async 直接使用，无需再次调用 LLM
        return req


# 模块级单例
intent_parser = IntentParser()

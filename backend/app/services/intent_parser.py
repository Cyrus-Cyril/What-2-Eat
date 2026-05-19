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
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import config
from app.models.schemas import RecommendRequest
from app.services.user_profile import get_user_profile
from app.services.llm_router import router as _llm_router

# ── 意图解析结果内存缓存（query → unified dict）───────────────────────
# 用于避免相同 query 重复调用 LLM，最多缓存 200 条
# 同时用 Lock 防止相同 query 并发触发多次 LLM 调用（thundering herd）
_MAX_CACHE_SIZE = 200
_intent_cache: dict[str, dict] = {}
_intent_locks: dict[str, asyncio.Lock] = {}  # per-query 锁

logger = logging.getLogger(__name__)


def _safe_float(v) -> float | None:
    """将 LLM 返回值安全转为 float，非数字类型静默返回 None。"""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

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


# ── 约束集 LLM Prompt（仅提取语义约束，基础参数已由规则提取）──────────
# 相比原版缩减约 50% token，加快 LLM prefill 与输出速度
_CONSTRAINT_PROMPT = """\
你是餐饮意图解析助手，只输出JSON，无需解释。
从用户输入提取语义约束集与意图摘要，格式（所有字段必填）：
{{"constraints":{{"tags":{{"values":[],"strength":"neutral","weight":0.2}},"price":{{"preferred":null,"max_limit":null,"strength":"neutral","weight":0.25,"tolerance":null}},"distance":{{"max_limit":null,"strength":"neutral","weight":0.3}},"rating":{{"strength":"neutral","weight":0.25}}}},"exclude_tags":[],"reason_hint":""}}
规则：
- strength枚举：required(必须/一定要/只能/不要) | preferred(想吃/喜欢/最好是/稍微) | neutral(未提及)
- preferred和max_limit必须是数字（单位：price为元，distance为米）或null，禁止输出字符串
- weight之和=1.0，按用户说话重心分配；exclude_tags为用户明确排斥的标签数组
用户输入："{query}"
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
    def _extract_params_by_rules(text: str) -> dict:
        """
        用正则/关键词从文本中快速提取基础参数（budget/radius/taste/scene），无需 LLM。
        结果与 LLM 约束集合并后写入缓存，供 parse() 直接使用。
        """
        _TASTE_KEYWORDS = (
            "川菜", "火锅", "日料", "寿司", "烧烤", "快餐", "西餐", "粤菜", "湘菜",
            "麻辣", "清淡", "甜品", "咖啡", "面条", "饺子", "烤肉", "海鲜", "早茶",
            "东北菜", "韩餐", "泰国菜", "汉堡", "披萨", "意面", "小吃", "夜宵", "早餐",
        )
        result: dict = {"budget_max": None, "budget_min": None,
                        "radius": None, "taste": [], "scene": None}

        # budget_max
        if re.search(r"很贵|高档|奢华", text):
            result["budget_max"] = 200
        elif re.search(r"便宜|实惠|划算|经济", text):
            result["budget_max"] = 30
        else:
            m = re.search(r"(\d+)\s*(?:元|块)(?:以内|内|左右)?|预算\s*(\d+)|不超过\s*(\d+)", text)
            if m:
                result["budget_max"] = int(next(v for v in m.groups() if v is not None))

        # budget_min
        m = re.search(r"(\d+)\s*(?:元|块)以上|至少\s*(\d+)", text)
        if m:
            result["budget_min"] = int(next(v for v in m.groups() if v is not None))

        # radius
        if re.search(r"很近|就在旁边|楼下", text):
            result["radius"] = 500
        elif re.search(r"附近|周边|旁边", text):
            result["radius"] = 1000
        elif re.search(r"远一点|稍远|不太远", text):
            result["radius"] = 3000
        else:
            m = re.search(r"(\d+(?:\.\d+)?)\s*公里", text)
            if m:
                result["radius"] = int(float(m.group(1)) * 1000)
            else:
                m = re.search(r"(\d+)\s*米", text)
                if m:
                    result["radius"] = int(m.group(1))

        # taste
        result["taste"] = [kw for kw in _TASTE_KEYWORDS if kw in text]

        # scene
        for kw, scene in (("聚餐", "聚餐"), ("约会", "约会"), ("商务", "商务"),
                          ("家庭", "家庭"), ("生日", "生日"),
                          ("一个人", "独食"), ("独自", "独食")):
            if kw in text:
                result["scene"] = scene
                break

        return result

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
                preferred=_safe_float(val.get("preferred")),
                max_limit=_safe_float(val.get("max_limit")),
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
        规则提取基础参数（budget/radius/taste）+ LLM 提取语义约束集，合并返回。
        使用共享多 Key 路由器 + 内存缓存 + per-query 锁（防 thundering herd）。
        LLM 失败时至少返回规则提取结果，保证降级有效。
        """
        cache_key = user_input.strip().lower()

        # ── 快速路径：缓存命中 ─────────────────────────────────────────
        if cache_key in _intent_cache:
            logger.debug("意图解析缓存命中: %s", cache_key[:30])
            return _intent_cache[cache_key]

        # ── 规则提取（本地，无 IO）─────────────────────────────────────
        rule_params = self._extract_params_by_rules(user_input)

        if not _llm_router.has_providers:
            logger.debug("LLM 未配置，仅返回规则提取参数")
            return rule_params

        # ── per-query 锁：同一 query 并发时只发起一次 LLM 调用 ──────────
        if cache_key not in _intent_locks:
            _intent_locks[cache_key] = asyncio.Lock()
        lock = _intent_locks[cache_key]

        async with lock:
            # 拿到锁后再检查一次缓存（可能已被前一个请求填充）
            if cache_key in _intent_cache:
                logger.debug("意图解析缓存命中（锁内）: %s", cache_key[:30])
                return _intent_cache[cache_key]

            prompt = _CONSTRAINT_PROMPT.format(query=user_input)
            try:
                content = await asyncio.wait_for(
                    _llm_router.call(prompt, timeout=12.0, max_tokens=300, temperature=0),
                    timeout=30.0,  # 含排队等待：12s HTTP + 18s 队列余量（允许等候1个完整调用周期）
                )
            except asyncio.TimeoutError:
                logger.warning("意图解析 LLM 调用全局超时（30s），降级为规则提取结果")
                return rule_params

            if not content:
                logger.warning("LLM 所有槽位不可用，意图解析降级为规则提取结果")
                return rule_params

            try:
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                llm_result = json.loads(content)
                logger.debug("LLM 约束集解析响应: %s", content[:200])
                # ── 合并：规则参数（Part A）+ LLM 约束集（Part B/C）────────
                result = {**rule_params, **llm_result}
                # ── 写入缓存（LRU 简易版：超上限时清除最旧一半）────────
                if len(_intent_cache) >= _MAX_CACHE_SIZE:
                    keys_to_remove = list(_intent_cache.keys())[:_MAX_CACHE_SIZE // 2]
                    for k in keys_to_remove:
                        del _intent_cache[k]
                        _intent_locks.pop(k, None)
                _intent_cache[cache_key] = result
                return result
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.warning("LLM 响应解析失败: %s", e)
        return rule_params

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

"""
app/services/intent_parser.py
自然语言意图解析 —— 调用 LLM 提取结构化参数，多源合并为 RecommendRequest
支持三层意图处理：
  Scene A (Context-Only)   — 无显式意图，按时间动态调整权重
  Scene B (Soft Boost)     — 模糊偏好，将 w_tag 提升 1.5x
  Scene C (Hard Filter)    — 明确品类/价格，先硬过滤候选集
"""
from __future__ import annotations

import json
import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Any

import httpx

import config
from app.models.schemas import RecommendRequest
from app.services.user_profile import get_user_profile

logger = logging.getLogger(__name__)

# ── 基础权重（与 scorer.py 保持一致）────────────────────────────────
_W_DISTANCE = 0.30
_W_PRICE    = 0.25
_W_RATING   = 0.25
_W_TAG      = 0.20


@dataclass
class IntentAnalysis:
    """
    analyze_intent() 的输出，驱动 recommender 的过滤与权重调整。

    intent_type:
        "context_only" — Scene A：无显式意图
        "soft_boost"   — Scene B：模糊偏好
        "hard_filter"  — Scene C：明确品类/价格
    filter_tags:        Scene C 硬过滤标签列表
    boost_tags:         Scene B 软加权标签（记录用，权重已写入 w_tag）
    filter_budget_max:  Scene C 价格上限（元）
    w_distance/price/rating/tag: 已根据场景调整好的有效权重（和为 1.0）
    """
    intent_type: str = "context_only"
    filter_tags: list[str] = field(default_factory=list)
    boost_tags: list[str] = field(default_factory=list)
    filter_budget_max: float | None = None
    w_distance: float = _W_DISTANCE
    w_price:    float = _W_PRICE
    w_rating:   float = _W_RATING
    w_tag:      float = _W_TAG
    # 标记是否由硬过滤空结果降级而来（供日志/explain 使用）
    fallback_from_hard_filter: bool = False



_LLM_PROMPT_TEMPLATE = """\
你是一个餐饮意图解析助手。请从用户的提问中提取以下信息并以标准 JSON 格式输出。
1. budget_max: 用户能接受的最高价格（数字，若提到"很贵"设200，"便宜"设30，否则 null）
2. budget_min: 用户能接受的最低价格（数字，否则 null）
3. radius: 搜索范围（数字，单位米。如"附近"设1000，"很近"设500，"远一点"设3000，否则 null）
4. taste: 提取口味或菜系关键词（字符串数组，如 ["川菜", "火锅"]，否则 []）
5. scene: 提取场景（如 "聚餐", "约会"，否则 null）

用户文字："{query}"

输出要求：只输出 JSON，严禁任何额外解释。\
"""

_INTENT_ANALYSIS_PROMPT = """\
你是一个餐饮意图分类助手。请分析用户输入，判断意图类型，并提取关键信息。

意图类型定义（三选一）：
- "context_only"  : 用户无特定标签、口味或价格表述（如"附近随便吃吃"、"推荐一下"、空输入）
- "soft_boost"    : 用户有模糊倾向但未指定具体品类（如"想吃点辣的"、"要便宜点"、"想吃清淡的"）
- "hard_filter"   : 用户明确指定品类或价格上限（如"吃火锅"、"川菜"、"30元以下"、"不超过50块"）

请提取：
1. intent_type       : 上述三种之一
2. filter_tags       : 硬过滤标签数组（仅 hard_filter 时填菜系/品类，如 ["火锅"] 或 ["川菜", "串串"]，否则 []）
3. boost_tags        : 软加权标签数组（仅 soft_boost 时填口味倾向，如 ["辣"] 或 ["清淡"]，否则 []）
4. filter_budget_max : 硬过滤价格上限（数字，仅用户明确说"X元以下/不超过X元"时填写，否则 null）

用户输入："{query}"

输出要求：只输出 JSON，严禁任何额外解释。
示例：{{"intent_type": "hard_filter", "filter_tags": ["火锅"], "boost_tags": [], "filter_budget_max": null}}
"""


class IntentParser:
    DEFAULT_VALUES: dict[str, Any] = {
        "longitude": 114.362,   # 默认光谷
        "latitude": 30.532,
        "radius": 2000,
        "budget_min": 0,
        "budget_max": 100,
        "taste": [],
        "max_count": 10,
    }

    # ── Scene A：工作日午餐权重 ───────────────────────────────────────
    _LUNCH_WEIGHTS = {"w_distance": 0.60, "w_price": 0.30, "w_rating": 0.10, "w_tag": 0.00}

    async def analyze_intent(
        self,
        user_input: str | None,
        context: dict | None = None,
    ) -> IntentAnalysis:
        """
        分析用户意图，返回 IntentAnalysis（过滤标签 + 动态权重）。

        优先级：
          1. 若 user_input 有内容 → 调用 LLM 分类（Scene A/B/C）
          2. 若 user_input 为空   → 直接判定为 Scene A（Context-Only）
          3. Scene A 时额外检查当前时间，工作日午餐覆盖权重
        """
        analysis = IntentAnalysis()

        # Step 1: LLM 分类（有文字输入时）
        llm_result: dict = {}
        if user_input and user_input.strip():
            llm_result = await self._call_intent_llm(user_input)

        intent_type = llm_result.get("intent_type", "context_only")
        if intent_type not in ("context_only", "soft_boost", "hard_filter"):
            intent_type = "context_only"
        analysis.intent_type = intent_type

        # Step 2: 根据场景填充字段
        if intent_type == "hard_filter":
            # Scene C: 提取硬过滤标签和价格上限
            raw_filter = llm_result.get("filter_tags", [])
            analysis.filter_tags = raw_filter if isinstance(raw_filter, list) else []
            raw_budget = llm_result.get("filter_budget_max")
            analysis.filter_budget_max = float(raw_budget) if raw_budget is not None else None
            # Scene C 使用默认权重，不调整
            analysis.w_distance = _W_DISTANCE
            analysis.w_price    = _W_PRICE
            analysis.w_rating   = _W_RATING
            analysis.w_tag      = _W_TAG

        elif intent_type == "soft_boost":
            # Scene B: 提取软加权标签，将 w_tag 乘以 1.5 并重新归一化
            raw_boost = llm_result.get("boost_tags", [])
            analysis.boost_tags = raw_boost if isinstance(raw_boost, list) else []
            w_tag_new = _W_TAG * 1.5
            # 其余三项按原比例瓜分剩余权重
            remaining = 1.0 - w_tag_new
            original_others = _W_DISTANCE + _W_PRICE + _W_RATING  # 0.80
            analysis.w_distance = round(remaining * (_W_DISTANCE / original_others), 4)
            analysis.w_price    = round(remaining * (_W_PRICE    / original_others), 4)
            analysis.w_rating   = round(remaining * (_W_RATING   / original_others), 4)
            analysis.w_tag      = round(w_tag_new, 4)

        else:
            # Scene A: 按时间动态调整权重
            now = (context or {}).get("now") or datetime.now()
            if self._is_weekday_lunch(now):
                analysis.w_distance = self._LUNCH_WEIGHTS["w_distance"]
                analysis.w_price    = self._LUNCH_WEIGHTS["w_price"]
                analysis.w_rating   = self._LUNCH_WEIGHTS["w_rating"]
                analysis.w_tag      = self._LUNCH_WEIGHTS["w_tag"]
                logger.debug("Scene A 午餐模式：w_d=0.60 w_p=0.30")
            else:
                analysis.w_distance = _W_DISTANCE
                analysis.w_price    = _W_PRICE
                analysis.w_rating   = _W_RATING
                analysis.w_tag      = _W_TAG

        return analysis

    def downgrade_to_soft_boost(self, analysis: IntentAnalysis) -> IntentAnalysis:
        """
        当 Scene C 硬过滤后候选集为空时，将原有的硬约束转化为软增强权重，
        保证推荐流程有结果输出。

        策略：
        - 将 filter_tags 挪入 boost_tags（在 scorer 中作为高权重偏好参与打分）
        - filter_tags / filter_budget_max 清空，不再做硬剔除
        - 根据是否有预算约束，分两套权重方案：
            有预算：品类(0.40) + 价格(0.45) + 距离(0.10) + 评分(0.05)
            无预算：品类(0.55) + 评分(0.20) + 距离(0.20) + 价格(0.05)
        - 标记 fallback_from_hard_filter = True
        """
        # 硬过滤标签合并进 boost_tags（保序去重）
        merged_boost = list(dict.fromkeys(analysis.boost_tags + analysis.filter_tags))

        has_budget = analysis.filter_budget_max is not None

        if has_budget:
            # 有预算约束：重心放在"品类最像"+"价格最近"
            w_tag      = 0.40
            w_price    = 0.45
            w_distance = 0.10
            w_rating   = 0.05
        else:
            # 仅有品类约束：重心放在"品类最像"，评分/距离次之
            w_tag      = 0.55
            w_price    = 0.05
            w_distance = 0.20
            w_rating   = 0.20

        analysis.boost_tags                = merged_boost
        analysis.filter_tags               = []    # 清除，不再硬剔除
        analysis.filter_budget_max         = None  # 清除价格硬限制
        analysis.w_tag                     = w_tag
        analysis.w_price                   = w_price
        analysis.w_distance                = w_distance
        analysis.w_rating                  = w_rating
        analysis.fallback_from_hard_filter = True

        logger.info(
            "硬过滤降级为软增强：boost_tags=%s has_budget=%s "
            "weights=[D=%.2f P=%.2f R=%.2f T=%.2f]",
            merged_boost, has_budget,
            w_distance, w_price, w_rating, w_tag,
        )
        return analysis

    @staticmethod
    def _is_weekday_lunch(now: datetime) -> bool:
        """工作日（周一至周五）11:00~13:30"""
        return now.weekday() < 5 and dtime(11, 0) <= now.time() <= dtime(13, 30)

    async def _call_intent_llm(self, user_input: str) -> dict:
        """调用 LLM 完成意图分类，3秒超时，失败返回空字典（降级为 context_only）"""
        if not config.LLM_API_KEY or not config.LLM_API_URL:
            logger.debug("LLM_API_KEY/URL 未配置，跳过意图分类")
            return {}

        prompt = _INTENT_ANALYSIS_PROMPT.format(query=user_input)
        payload = {
            "model": config.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                url = config.LLM_API_URL
                if not url.endswith("/chat/completions"):
                    url = f"{url.rstrip('/')}/chat/completions"
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                return json.loads(content)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning("意图分类 LLM 调用失败（%s），降级为 context_only", type(e).__name__)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("意图分类 LLM 响应解析失败: %s", e)
        return {}

    async def parse(
        self,
        user_id: str | None,
        query: str | None,
        raw_params: dict,
    ) -> RecommendRequest:
        """
        多源参数合并：Query(LLM) > Raw Params > History > Default
        """
        # Step 1: LLM 解析自然语言
        query_intent: dict = {}
        if query and query.strip():
            query_intent = await self._call_llm(query)

        # Step 2: 获取历史偏好（有 user_id 时才查询）
        history_profile: dict = {}
        if user_id:
            history_profile = await get_user_profile(user_id)

        # Step 3: 合并参数
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

        # 预算/范围：Query > 前端 > 历史 > 默认
        for key in ["budget_min", "budget_max", "radius"]:
            final[key] = (
                query_intent.get(key)
                or raw_params.get(key)
                or history_profile.get(f"avg_{key}")
                or self.DEFAULT_VALUES[key]
            )

        # 口味：Query + 前端 的并集；都无时用历史
        taste_set: set[str] = set()
        llm_taste = query_intent.get("taste", [])
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

        # taste 以逗号分隔字符串传入 RecommendRequest
        final["taste"] = ",".join(taste_set) if taste_set else None

        # max_count：前端传值 > 默认
        final["max_count"] = raw_params.get("max_count") or self.DEFAULT_VALUES["max_count"]
        final["max_distance"] = raw_params.get("max_distance")
        final["query"] = query

        return RecommendRequest(user_id=user_id, **final)

    async def _call_llm(self, query: str) -> dict:
        """调用 LLM API 解析 query，3秒超时，失败返回空字典"""
        if not config.LLM_API_KEY or not config.LLM_API_URL:
            logger.debug("LLM_API_KEY/URL 未配置，跳过 LLM 解析")
            return {}

        prompt = _LLM_PROMPT_TEMPLATE.format(query=query)
        payload = {
            "model": config.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {config.LLM_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 拼接完整路径，确保兼容性
                url = config.LLM_API_URL
                if not url.endswith("/chat/completions"):
                    url = f"{url.rstrip('/')}/chat/completions"
                
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 404:
                    logger.warning("LLM URL 404，请确认 API URL 是否正确（当前尝试: %s）", url)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # 去除 markdown 代码块包装
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                return json.loads(content)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning("LLM 调用失败（%s），降级为空意图", type(e).__name__)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("LLM 响应解析失败: %s", e)
        return {}


# 模块级单例
intent_parser = IntentParser()

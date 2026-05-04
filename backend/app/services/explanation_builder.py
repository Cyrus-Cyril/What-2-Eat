"""
app/services/explanation_builder.py
解释系统构建器 —— 全局 ExplanationSystem + 个体 ai_speech

设计原则：计算归规则，表达归 AI。
LLM 调用失败时均降级为规则模板，保证可用性。
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

import config
from app.services.explainer import ExplainData as LocalExplainData
from app.services.intent_parser import IntentAnalysis
from app.models.schemas import (
    StructuredContext,
    ExplanationSystem,
    DimensionDetail,
    ReasoningLogic,
)

logger = logging.getLogger(__name__)

# ── 场景描述映射 ──────────────────────────────────────────
_SCENE_LABELS: dict[str, str] = {
    "context_only": "Scene A - 环境感知推荐",
    "soft_boost":   "Scene B - 偏好加权推荐",
    "hard_filter":  "Scene C - 精准品类筛选",
}

# ── 规则模板（fallback） ───────────────────────────────────
_WELCOME_TEMPLATES: dict[str, str] = {
    "context_only": (
        "好的！我根据您当前的位置，为您推荐了附近综合评价最佳的餐厅，"
        "兼顾距离、价格和口碑，希望您用餐愉快！"
    ),
    "soft_boost": (
        "明白了！我已根据您的口味偏好，优先筛选出最符合您喜好的餐厅，"
        "同时兼顾了距离和价格因素，为您定制了这份推荐列表。"
    ),
    "hard_filter": (
        "好的！我已精准筛选出所有符合您指定品类和预算的餐厅，"
        "并按综合评分为您排序，请查看以下推荐结果。"
    ),
    "hard_filter_fallback": (
        "抱歉，附近暂时没有完全符合您要求的餐厅。"
        "不过别担心，我已切换为偏好加权模式，为您推荐最接近您口味的选择。"
    ),
}

# ── LLM Prompt ────────────────────────────────────────────
_WELCOME_PROMPT_TEMPLATE = """\
你是一个贴心的美食导览助手。请根据用户本次推荐请求的意图信息，用1-2句自然流畅的中文生成一段"开场白"。

意图信息：
- 场景模式：{intent_mode}
- 核心关键词：{core_tags_str}
- 权重调整：{weights_str}
- 是否由硬过滤降级：{fallback}

要求：
1. 语气亲切自然，像一位了解用户需求的助手。
2. 必须体现用户的核心诉求（关键词、场景）。
3. 只输出开场白文本，不要任何JSON或额外解释。
4. 字数控制在50字以内。\
"""

_AI_SPEECH_PROMPT_TEMPLATE = """\
你是一个精明、贴心的美食导览助手。请根据以下餐厅数据，用1-3句话生成推荐理由。

餐厅名称：{name}
主要优势：{primary_factor}
次要优势：{secondary_factor}
各维度详情：
{dimension_details_str}

生成规则：
1. 必须包含证据链：每个提到的理由必须来自"score_impact=high"的维度数据。
2. 若有score_impact=low的维度，必须用"虽然...但是..."句式提及。
3. 严禁描述数据中不存在的属性（禁止幻觉）。
4. 语言简洁自然，字数控制在60字以内。
5. 只输出推荐话术文本，不要任何JSON或额外解释。\
"""


async def _call_llm(prompt: str, timeout: float = 3.0) -> str | None:
    """调用 LLM API，返回生成文本；超时或失败返回 None。"""
    if not config.LLM_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{config.LLM_API_URL}/chat/completions",
                headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                json={
                    "model": config.LLM_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.debug("LLM 调用失败，降级为规则模板: %s", exc)
        return None


def _build_structured_context(
    intent: IntentAnalysis,
) -> StructuredContext:
    """根据意图分析结果构建结构化上下文（纯规则）。"""
    scene_label = _SCENE_LABELS.get(intent.intent_type, intent.intent_type)
    if intent.fallback_from_hard_filter:
        scene_label += "（已降级为软增强）"

    core_tags = list(intent.filter_tags or intent.boost_tags or [])

    adjusted_weights = {
        "distance": f"{intent.w_distance:.2f}",
        "price":    f"{intent.w_price:.2f}",
        "rating":   f"{intent.w_rating:.2f}",
        "tag":      f"{intent.w_tag:.2f}",
    }

    return StructuredContext(
        intent_mode=scene_label,
        core_tags=core_tags,
        adjusted_weights=adjusted_weights,
    )


async def build_explanation_system(
    intent: IntentAnalysis,
    req_query: str | None,
    result_count: int,
) -> ExplanationSystem:
    """
    构建全局解释系统：
    - 规则生成 StructuredContext
    - LLM（3s 超时）生成 welcome_narrative，失败降级为规则模板
    """
    structured_context = _build_structured_context(intent)

    # 构建 LLM prompt
    core_tags_str = "、".join(structured_context.core_tags) if structured_context.core_tags else "无"
    weights_str = "、".join(f"{k}={v}" for k, v in structured_context.adjusted_weights.items())
    prompt = _WELCOME_PROMPT_TEMPLATE.format(
        intent_mode=structured_context.intent_mode,
        core_tags_str=core_tags_str,
        weights_str=weights_str,
        fallback="是" if intent.fallback_from_hard_filter else "否",
    )

    welcome_narrative = await _call_llm(prompt, timeout=3.0)

    # LLM 失败 → 规则降级
    if not welcome_narrative:
        if intent.fallback_from_hard_filter:
            welcome_narrative = _WELCOME_TEMPLATES["hard_filter_fallback"]
        else:
            welcome_narrative = _WELCOME_TEMPLATES.get(
                intent.intent_type,
                _WELCOME_TEMPLATES["context_only"],
            )

    return ExplanationSystem(
        welcome_narrative=welcome_narrative,
        structured_context=structured_context,
    )


async def build_ai_speech(
    restaurant_name: str,
    dimension_details: list[DimensionDetail],
    reasoning_logic: ReasoningLogic | None,
) -> str | None:
    """
    为单个餐厅生成 ai_speech（LLM，2s 超时，失败返回 None）。
    """
    if not dimension_details:
        return None

    primary = reasoning_logic.primary_factor if reasoning_logic else ""
    secondary = reasoning_logic.secondary_factor if reasoning_logic else ""

    details_lines = "\n".join(
        f"  - {d.dimension}：{d.detail}（影响={d.score_impact}）"
        for d in dimension_details
    )

    prompt = _AI_SPEECH_PROMPT_TEMPLATE.format(
        name=restaurant_name,
        primary_factor=primary,
        secondary_factor=secondary or "无",
        dimension_details_str=details_lines,
    )

    return await _call_llm(prompt, timeout=2.0)


async def build_ai_speeches_for_top_n(
    restaurants: list[dict],
) -> list[str | None]:
    """
    并发为 top_n 餐厅生成 ai_speech。
    restaurants 列表中每项包含：name, dimension_details, reasoning_logic
    """
    tasks = [
        build_ai_speech(
            r["name"],
            r["dimension_details"],
            r["reasoning_logic"],
        )
        for r in restaurants
    ]
    return list(await asyncio.gather(*tasks))

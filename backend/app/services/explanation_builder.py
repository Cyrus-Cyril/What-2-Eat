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

import config
from typing import Optional
from app.services.explainer import ExplainData as LocalExplainData
from app.services.intent_parser import IntentConstraint
from app.services.llm_router import router as _router
from app.models.schemas import (
    StructuredContext,
    ExplanationSystem,
    DimensionDetail,
    ReasoningLogic,
)

logger = logging.getLogger(__name__)

# ── 欢迎语内存缓存（intent_key → hello_voice）─────────────────────
# 相同意图模式+标签组合复用 LLM 结果，TTL 通过 LRU 上限控制
_HELLO_CACHE_MAX = 100
_hello_cache: dict[str, str] = {}

# ── 场景描述映射 ──────────────────────────────────────────
_SCENE_LABELS: dict[str, str] = {
    "required": "精准约束推荐",
    "preferred": "偏好导向推荐",
    "neutral":  "综合评分推荐",
    "fallback": "兜底偏好推荐（已松弛限制）",
}

# ── 规则模板（fallback） ───────────────────────────────────
_WELCOME_TEMPLATES: dict[str, str] = {
    "neutral": (
        "好嘞！我扫了一眼你周围，给你挑了几家离得近、口碑不错的餐厅，"
        "价格也还算实在，应该都合适哈！"
    ),
    "preferred": (
        "懂你！我按你的口味倾向优先给你捞出来了，"
        "距离和价格也都照顾到了，这几家应该都对你胃口！"
    ),
    "required": (
        "搞定！我已经把完全符合你要求的都给你筛出来了，"
        "按综合评分排好序了，几家都挺不错哈！"
    ),
    "fallback": (
        "哎，附近暂时没找到完全符合要求的……别担心，"
        "我已经自动放宽限制给你找最接近的了，应该也差不多嘛！"
    ),
}

# ── LLM Prompt ────────────────────────────────────────────
_WELCOME_PROMPT_TEMPLATE = """\
你是一个有点小幽默、懂吃又懂生活的美食密友。你说话直白坦诚，不讲大道理，更像是在微信上给好朋友发语音推荐餐厅。

【重要】你现在的角色是：已经帮用户找好餐厅了，正在告诉用户"我是怎么帮你找的、找到了什么"。
你是在向用户介绍推荐结果，不是在问用户问题，也不是在询问用户有什么推荐。

请根据以下意图信息，用1-2句话生成一段轻松的"开场白"，说明你是如何为用户筛选的：

意图信息：
- 场景模式：{intent_mode}
- 核心关键词：{core_tags_str}
- 权重调整：{weights_str}
- 是否由硬过滤降级：{fallback}
- 系统调整说明（若非"无"，必须在开场白中坦诚提及）：{relaxation_note}
- 用户近期偏好上下文（若非"无"，可自然融入一句话）：{feedback_note}

语言规则：
1. 严禁出现"基于您的偏好"、"匹配度"、"加权计算"、"归一化"等词汇。
2. 严禁以问句结尾（不要问用户任何问题）。
3. 多用语气助词"哈、哇、嘛、咯、吧"，增加对话感。
4. 若"系统调整说明"非"无"，必须用口语化方式坦白（如"贵了点但值得"、"没火锅就找了个接近的"）。
5. 若"用户近期偏好上下文"非"无"，可在开场白中自然融入（如"你之前赞过川菜，这次我特意多找了几家"）。
6. 只输出开场白文本，不要任何JSON或额外解释。
7. 字数控制在70字以内。\
"""

_AI_SPEECH_PROMPT_TEMPLATE = """\
你是一个有点小幽默、懂吃又懂生活的美食密友。你说话直白坦诚，不讲大道理，更像是在微信上给好朋友发语音推荐餐厅。

请根据以下餐厅数据，用1-3句话生成推荐理由。

餐厅名称：{name}
主要优势：{primary_factor}
次要优势：{secondary_factor}
各维度详情：
{dimension_details_str}

语言规则：
1. 严禁出现"基于您的偏好"、"匹配度"、"加权计算"、"归一化"等词汇。
2. 多用语气助词"哈、哇、嘛、咯、吧"，增加对话感。
3. 情绪化表达：不要说"距离分数高"，要说"这家就在你楼下，懒人必备！"
4. 坦诚转折：若有score_impact=low的维度，必须用"虽然...但..."句式坦诚提及，不要掩盖。
5. 每个提到的理由必须来自score_impact=high的维度数据，不得编造不存在的属性。
6. 字数控制在60字以内，只输出推荐话术，不要任何JSON或额外解释。\
"""

_BATCH_AI_SPEECH_PROMPT_TEMPLATE = """\
你是一个有点小幽默、懂吃又懂生活的美食密友。请为以下{count}家餐厅分别生成1-3句推荐理由。

{restaurants_info}

语言规则：
1. 严禁出现"基于您的偏好"、"匹配度"、"加权计算"、"归一化"等词汇。
2. 多用语气助词"哈、哇、嘛、咯、吧"，增加对话感。
3. 情绪化表达，不要平铺直叙。
4. 字数每条控制在60字以内。
5. 只输出JSON数组，数组长度必须等于{count}，格式：["第1家推荐语","第2家推荐语",...]，不要任何解释。\
"""


async def _call_llm(
    prompt: str,
    timeout: float = 3.0,
    total_timeout: float | None = None,
    max_tokens: int = 120,
) -> str | None:
    """
    调用 LLM API（共享多 Key 路由器），失败返回 None。

    参数：
        timeout:       单次 HTTP 请求超时（秒）
        total_timeout: 含排队等待的总超时（秒）；
                       默认为 timeout + 5s，避免信号量排队导致无限阻塞
    """
    wall_clock = total_timeout if total_timeout is not None else (timeout + 5.0)
    try:
        return await asyncio.wait_for(
            _router.call(prompt, timeout=timeout, max_tokens=max_tokens, temperature=0.7),
            timeout=wall_clock,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "LLM 调用总超时（含排队 %.1fs），直接降级为规则模板", wall_clock
        )
        return None


def _build_structured_context(
    intent: IntentConstraint,
) -> StructuredContext:
    """根据 IntentConstraint 构建结构化上下文（纯规则）。"""
    if intent.fallback_applied:
        scene_label = _SCENE_LABELS["fallback"]
    else:
        strengths = [c.strength for c in intent.constraints.values()]
        if "required" in strengths:
            scene_label = _SCENE_LABELS["required"]
        elif "preferred" in strengths:
            scene_label = _SCENE_LABELS["preferred"]
        else:
            scene_label = _SCENE_LABELS["neutral"]

    tags_c = intent.constraints.get("tags")
    core_tags = list(tags_c.values) if tags_c and tags_c.values else []

    adjusted_weights = {
        dim: f"{c.weight:.2f}" for dim, c in intent.constraints.items()
    }

    return StructuredContext(
        intent_mode=scene_label,
        core_tags=core_tags,
        adjusted_weights=adjusted_weights,
    )


def _build_feedback_note(ctx: dict | None) -> str:
    """
    将近期反馈上下文（liked_tags / disliked_tags）转为一句人类可读的提示，
    注入 LLM prompt 的 {feedback_note} 占位符。
    """
    if not ctx:
        return ""
    liked = ctx.get("liked_tags", [])
    disliked = ctx.get("disliked_tags", [])
    parts: list[str] = []
    if liked:
        parts.append(f"用户最近赞过「{'、'.join(liked[:3])}」")
    if disliked:
        parts.append(f"用户不太想吃「{'、'.join(disliked[:3])}」（已避开）")
    return "；".join(parts)


async def build_explanation_system(
    intent: IntentConstraint,
    req_query: str | None,
    result_count: int,
    fallback_note: str = "",
    recent_feedback_context: dict | None = None,
) -> ExplanationSystem:
    """
    构建全局解释系统：
    - 规则生成 StructuredContext
    - LLM（3s 超时）生成 hello_voice，失败降级为规则模板
    - 若兜底触发（fallback_note 非空），在 hello_voice 中坦白告知
    - 若用户有近期反馈（LIKE/DISLIKE），在 hello_voice 中自然提及
    """
    structured_context = _build_structured_context(intent)

    # 兜底/约束调整说明（坦诚告知用户系统做了哪些调整）
    relaxation_note = fallback_note or intent.reason_hint or ""

    # 近期反馈上下文摘要
    feedback_note = _build_feedback_note(recent_feedback_context)

    # 约束强度摘要（供 LLM prompt 使用）
    required_dims = [
        f"{dim}({','.join(c.values) if c.values else str(c.max_limit)})"
        for dim, c in intent.constraints.items()
        if c.strength == "required"
    ]
    preferred_dims = [
        f"{dim}({','.join(c.values) if c.values else str(c.preferred or c.max_limit)})"
        for dim, c in intent.constraints.items()
        if c.strength == "preferred"
    ]
    constraint_str = "；".join(
        ([f"必须:{','.join(required_dims)}"] if required_dims else []) +
        ([f"偏好:{','.join(preferred_dims)}"] if preferred_dims else [])
    ) or "无特定约束"

    core_tags_str = "、".join(structured_context.core_tags) if structured_context.core_tags else "无"
    weights_str = "、".join(f"{k}={v}" for k, v in structured_context.adjusted_weights.items())
    prompt = _WELCOME_PROMPT_TEMPLATE.format(
        intent_mode=structured_context.intent_mode,
        core_tags_str=core_tags_str,
        weights_str=weights_str,
        fallback="是" if intent.fallback_applied else "否",
        relaxation_note=relaxation_note if relaxation_note else "无",
        feedback_note=feedback_note if feedback_note else "无",
    )

    # ── 欢迎语缓存：相同意图模式+标签+反馈直接复用 ──────────────────
    _hello_cache_key = f"{structured_context.intent_mode}|{core_tags_str}|{feedback_note[:30]}"
    hello_voice = _hello_cache.get(_hello_cache_key)
    if hello_voice:
        logger.debug("欢迎语缓存命中: %s", _hello_cache_key[:40])
    else:
        hello_voice = await _call_llm(prompt, timeout=3.0)
        if hello_voice:
            # 简单 LRU：超限时清除最旧一半
            if len(_hello_cache) >= _HELLO_CACHE_MAX:
                for k in list(_hello_cache.keys())[:_HELLO_CACHE_MAX // 2]:
                    del _hello_cache[k]
            _hello_cache[_hello_cache_key] = hello_voice

    # LLM 失败 → 规则降级
    if not hello_voice:
        if intent.fallback_applied:
            hello_voice = _WELCOME_TEMPLATES["fallback"]
        else:
            strengths = [c.strength for c in intent.constraints.values()]
            if "required" in strengths:
                hello_voice = _WELCOME_TEMPLATES["required"]
            elif "preferred" in strengths:
                hello_voice = _WELCOME_TEMPLATES["preferred"]
            else:
                hello_voice = _WELCOME_TEMPLATES["neutral"]

    my_logic: dict | None = None
    if fallback_note or intent.fallback_applied:
        my_logic = {
            "fallback_applied": intent.fallback_applied,
            "note": fallback_note or "已松弛 required 约束为 preferred",
            "reason_hint": intent.reason_hint,
        }

    return ExplanationSystem(
        hello_voice=hello_voice,
        structured_context=structured_context,
        my_logic=my_logic,
    )


async def build_ai_speech(
    restaurant_name: str,
    match_details: list[DimensionDetail],
    reasoning_logic: ReasoningLogic | None,
) -> str | None:
    """
    为单个餐厅生成 ai_speech（LLM，2s 超时，失败返回 None）。
    仅在单独调用时使用；批量场景请用 build_ai_speeches_for_top_n。
    """
    if not match_details:
        return None

    primary = reasoning_logic.primary_factor if reasoning_logic else ""
    secondary = reasoning_logic.secondary_factor if reasoning_logic else ""

    details_lines = "\n".join(
        f"  - {d.dimension}：{d.detail}（影响={d.score_impact}）"
        for d in match_details
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
    批量为 top_n 餐厅生成 ai_speech —— 单次 LLM 调用（原来是 N 次并发调用）。
    大幅降低高并发下的 LLM 请求数：max_count=6 时从 6 次减少到 1 次。
    失败时降级为全 None（调用方不展示 ai_speech 即可）。
    restaurants 列表中每项包含：name, match_details, reasoning_logic
    """
    if not restaurants:
        return []

    # 组装每家餐厅的简要描述
    parts: list[str] = []
    for i, r in enumerate(restaurants, 1):
        match_details: list[DimensionDetail] = r.get("match_details", [])
        reasoning_logic: Optional[ReasoningLogic] = r.get("reasoning_logic")
        primary = reasoning_logic.primary_factor if reasoning_logic else ""
        secondary = reasoning_logic.secondary_factor if reasoning_logic else ""
        details_lines = "；".join(
            f"{d.dimension}({d.score_impact})"
            for d in match_details
        ) or "无"
        parts.append(
            f"[{i}] 餐厅：{r['name']}｜主要优势：{primary}｜次要：{secondary or '无'}｜维度：{details_lines}"
        )

    count = len(restaurants)
    prompt = _BATCH_AI_SPEECH_PROMPT_TEMPLATE.format(
        count=count,
        restaurants_info="\n".join(parts),
    )

    # 批量调用：超时适当放宽（count 越多，max_tokens 越多）
    # total_timeout = HTTP超时(4s) + 排队余量(6s) = 10s，超时直接降级为全 None
    max_tokens = min(100 * count, 800)
    try:
        raw = await asyncio.wait_for(
            _router.call(prompt, timeout=4.0, max_tokens=max_tokens, temperature=0.7),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.warning("批量 ai_speech 总超时（含排队 10s），降级为全 None")
        return [None] * count
    if not raw:
        return [None] * count

    try:
        # 去除可能的 markdown 代码块包裹
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        speeches: list = json.loads(cleaned)
        if isinstance(speeches, list) and len(speeches) == count:
            return [str(s) if s else None for s in speeches]
        # 长度不匹配时取能对应的部分，剩余补 None
        result = [str(speeches[i]) if i < len(speeches) and speeches[i] else None for i in range(count)]
        return result
    except Exception as exc:
        logger.warning("批量 ai_speech 解析失败（%s），降级为 None", exc)
        return [None] * count

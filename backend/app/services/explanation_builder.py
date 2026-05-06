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
        "好嘞！我扫了一眼你周围，给你挑了几家离得近、口碑不错的餐厅，"
        "价格也还算实在，应该都合适哈！"
    ),
    "soft_boost": (
        "懂你！我按你平时的口味优先给你捞出来了，"
        "距离和价格也都照顾到了，这几家应该都对你胃口！"
    ),
    "hard_filter": (
        "搞定！我已经把符合你要求的都给你筛出来了，"
        "按综合评分排好序了，几家都挺不错哈！"
    ),
    "hard_filter_fallback": (
        "哎，附近暂时没找到完全符合要求的……别担心，"
        "我已经切换模式给你找最接近的了，应该也差不多嘛！"
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
    intent: IntentAnalysis,
    req_query: str | None,
    result_count: int,
    relaxation_info: dict | None = None,
    recent_feedback_context: dict | None = None,
) -> ExplanationSystem:
    """
    构建全局解释系统：
    - 规则生成 StructuredContext 和 my_logic（松弛策略摘要）
    - LLM（3s 超时）生成 hello_voice，失败降级为规则模板
    - 若松弛搜索有坦诚告知内容（如预算放宽），注入 hello_voice
    - 若用户有近期反馈（LIKE/DISLIKE），在 hello_voice 中自然提及
    """
    structured_context = _build_structured_context(intent)
    my_logic = relaxation_info if relaxation_info else None

    # 松弛告知前缀（坦诚告知用户系统做了哪些调整）
    relaxation_note = (relaxation_info or {}).get("note", "")

    # 近期反馈上下文摘要
    feedback_note = _build_feedback_note(recent_feedback_context)

    # 构建 LLM prompt
    core_tags_str = "、".join(structured_context.core_tags) if structured_context.core_tags else "无"
    weights_str = "、".join(f"{k}={v}" for k, v in structured_context.adjusted_weights.items())
    prompt = _WELCOME_PROMPT_TEMPLATE.format(
        intent_mode=structured_context.intent_mode,
        core_tags_str=core_tags_str,
        weights_str=weights_str,
        fallback="是" if intent.fallback_from_hard_filter else "否",
        relaxation_note=relaxation_note if relaxation_note else "无",
        feedback_note=feedback_note if feedback_note else "无",
    )

    hello_voice = await _call_llm(prompt, timeout=3.0)

    # LLM 失败 → 规则降级
    if not hello_voice:
        if intent.fallback_from_hard_filter:
            hello_voice = _WELCOME_TEMPLATES["hard_filter_fallback"]
        else:
            hello_voice = _WELCOME_TEMPLATES.get(
                intent.intent_type,
                _WELCOME_TEMPLATES["context_only"],
            )

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
    并发为 top_n 餐厅生成 ai_speech。
    restaurants 列表中每项包含：name, match_details, reasoning_logic
    """
    tasks = [
        build_ai_speech(
            r["name"],
            r["match_details"],
            r["reasoning_logic"],
        )
        for r in restaurants
    ]
    return list(await asyncio.gather(*tasks))

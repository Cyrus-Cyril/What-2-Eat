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
import re

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

请根据以下餐厅数据，用2-4句话生成推荐理由，内容要具体、有画面感。

餐厅名称：{name}
主要优势：{primary_factor}
次要优势：{secondary_factor}
各维度详情：
{dimension_details_str}

语言规则：
1. 严禁出现"基于您的偏好"、"匹配度"、"加权计算"、"归一化"等词汇。
2. 多用语气助词"哈、哇、嘛、咯、吧"，增加对话感。
3. 情绪化表达：把数据变成画面，如"距离200米"→"走出门口就到"，"人均40"→"一顿午饭的价格"。
4. 具体细节优先：优先引用维度详情中的具体数字、菜品、标签等信息，让人读完就有感觉。
5. 坦诚转折：若有score_impact=low的维度，必须用"虽然...但..."句式坦诚提及，不要掩盖。
6. 适合场景：结尾补一句适合什么情况去（如"约会"、"一个人吃"、"带孩子"、"快节奏午饭"）。
7. 每个提到的理由必须来自维度数据，不得编造不存在的属性。
8. 字数控制在100字以内，只输出推荐话术，不要任何JSON或额外解释。\"""
"""

_BATCH_AI_SPEECH_PROMPT_TEMPLATE = """\
你是一个有点小幽默、懂吃又懂生活的美食密友。请为以下{count}家餐厅分别生成2-4句推荐理由，内容要具体、有画面感。

{restaurants_info}

语言规则：
1. 严禁出现"基于您的偏好"、"匹配度"、"加权计算"、"归一化"等词汇。
2. 多用语气助词"哈、哇、嘛、咯、吧"，增加对话感。
3. 情绪化表达：把数据变成画面，如"距离200米"→"走出门口就到"，"人均40"→"一顿午饭的价格"。
4. 具体细节优先：优先引用各维度的具体描述（菜品、标签、距离数字、价格区间等）。
5. 坦诚转折：若某项表现一般，用"虽然...但..."句式自然带过，不掩盖。
6. 结尾补一句适合的场景或人群，让推荐更有温度。
7. 每条字数控制在100字以内。
8. 只输出JSON数组，数组长度必须等于{count}，格式：["第1家推荐语","第2家推荐语",...]，不要任何解释。\"""
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
    fast_mode: bool = False,
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
    elif fast_mode:
        hello_voice = None  # 极速模式：直接跳过 LLM，使用规则模板
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
    为单个餐厅生成 ai_speech（LLM，10s 超时，失败返回 None）。
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

    result = await _call_llm(prompt, timeout=12.0, max_tokens=200)
    if result:
        return result

    # LLM 失败或超时：降级为规则模板，基于 match_details 和 reasoning_logic 生成简短语句
    try:
        parts: list[str] = []
        # 取最重要的两条 match_details
        if match_details:
            primary = match_details[0]
            parts.append(f"{restaurant_name}，{primary.dimension}：{primary.detail}")
            if len(match_details) > 1:
                secondary = match_details[1]
                parts.append(f"此外{secondary.dimension}：{secondary.detail}")

        # reasoning_logic 补充场景说明
        if reasoning_logic and reasoning_logic.primary_factor:
            parts.append(f"推荐理由：{reasoning_logic.primary_factor.split('：')[-1]}")

        # 组合为 2-4 句的自然话术，保证不超过 100 字
        fallback = '。'.join(parts)
        if not fallback:
            fallback = f"{restaurant_name}，综合表现不错，适合随性尝试。"
        if len(fallback) > 100:
            fallback = fallback[:97] + '...'
        return fallback
    except Exception:
        logger.exception("生成 ai_speech 的规则降级模板失败")
        return None


async def _build_ai_speeches_batch(
    restaurants: list[dict],
) -> list[str | None] | None:
    """
    批量 LLM 调用：一次请求生成所有餐厅的推荐语，返回字符串列表。
    JSON 解析失败或 LLM 失败时返回 None（调用方应降级到逐条模式）。
    相比逐条并发，优点：
      - 只占用 1 个信号量槽位，不造成排队积压
      - 总耗时约等于单次 LLM 调用时间（而非 N 次）
    """
    count = len(restaurants)

    # 构建每家餐厅的描述块
    blocks: list[str] = []
    for i, r in enumerate(restaurants, start=1):
        match_details: list[DimensionDetail] = r.get("match_details", [])
        reasoning_logic: Optional[ReasoningLogic] = r.get("reasoning_logic")

        details_lines = "\n".join(
            f"  - {d.dimension}：{d.detail}（影响={d.score_impact}）"
            for d in match_details
        ) or "  - 暂无详细数据"

        primary = reasoning_logic.primary_factor if reasoning_logic else "综合评分"
        secondary = (
            reasoning_logic.secondary_factor
            if reasoning_logic and reasoning_logic.secondary_factor
            else "无"
        )

        blocks.append(
            f"【餐厅{i}】{r['name']}\n"
            f"主要优势：{primary}\n"
            f"次要优势：{secondary}\n"
            f"各维度详情：\n{details_lines}"
        )

    restaurants_info = "\n\n".join(blocks)
    prompt = _BATCH_AI_SPEECH_PROMPT_TEMPLATE.format(
        count=count,
        restaurants_info=restaurants_info,
    )

    # 批量调用：每家餐厅约 3s 生成余量 + 12s 底线，max_tokens 按 N 家线性放大
    per_request_timeout = max(count * 3.0 + 12.0, 20.0)
    total_timeout = per_request_timeout + 8.0
    max_tokens = count * 120

    raw = await _call_llm(
        prompt,
        timeout=per_request_timeout,
        total_timeout=total_timeout,
        max_tokens=max_tokens,
    )
    if not raw:
        return None

    # 解析 JSON 数组（兼容 LLM 在输出前后附加 markdown 代码块的情况）
    try:
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        raw_json = m.group(0) if m else raw
        speeches = json.loads(raw_json)
        if not isinstance(speeches, list) or len(speeches) != count:
            logger.warning(
                "批量 ai_speech 返回长度不符 expected=%d got=%s",
                count,
                len(speeches) if isinstance(speeches, list) else type(speeches).__name__,
            )
            return None
        return [s if isinstance(s, str) else None for s in speeches]
    except Exception as exc:
        logger.warning("批量 ai_speech JSON 解析失败: %s | raw=%.200s", exc, raw)
        return None


async def build_ai_speeches_for_top_n(
    restaurants: list[dict],
) -> list[str | None]:
    """
    为 top_n 餐厅批量生成 ai_speech，三层策略保证成功率：

    1. 批量 LLM 调用（1 次请求 N 家，只占 1 个信号量槽位，成功率高）
    2. 批量失败时降级为逐条并发 LLM 调用
    3. 每条 LLM 失败时进一步降级为规则模板（build_ai_speech 内已实现）
    """
    if not restaurants:
        return []

    # ── 策略1：批量调用 ──────────────────────────────────────────────
    if len(restaurants) > 1:
        batch_result = await _build_ai_speeches_batch(restaurants)
        if batch_result is not None:
            logger.debug("批量 ai_speech 生成成功 count=%d", len(batch_result))
            return batch_result
        logger.warning("批量 ai_speech 失败，降级为逐条并发调用")

    # ── 策略2：逐条并发调用（每条内部仍有规则降级） ──────────────────
    async def _one(r: dict) -> str | None:
        match_details: list[DimensionDetail] = r.get("match_details", [])
        reasoning_logic: Optional[ReasoningLogic] = r.get("reasoning_logic")
        return await build_ai_speech(r["name"], match_details, reasoning_logic)

    results = await asyncio.gather(*[_one(r) for r in restaurants], return_exceptions=True)
    out: list[str | None] = []
    for r in results:
        if isinstance(r, str):
            out.append(r)
        else:
            out.append(None)
    return out

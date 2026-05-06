"""
app/services/scorer.py
各维度打分逻辑 —— 严格按设计文档公式实现

公式：
  DistanceScore = max(0, 1 - distance_m / max_dist)
  PriceScore    = exp(-|price - mid_budget| / tolerance)
  RatingScore   = rating / 5.0
  TagScore      = 基于标签匹配（融合当下意图 + 历史偏好）
  FinalScore    = 0.30*D + 0.25*P + 0.25*R + 0.20*T
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.models.schemas import RecommendRequest
from app.services.tag_mapper import get_tags


@dataclass
class ScoreDetail:
    distance: float = 0.0
    price: float = 0.5
    rating: float = 0.4
    tag: float = 0.5
    final: float = 0.0
    matched_tags: list[str] = field(default_factory=list)


# 权重（之和 = 1.0）
W_DISTANCE = 0.30
W_PRICE = 0.25
W_RATING = 0.25
W_TAG = 0.20


def calc_all(
    restaurant: dict,
    req: RecommendRequest,
    user_tag_preferences: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    penalty_factor: float = 1.0,
    filter_budget_max: float | None = None,
) -> ScoreDetail:
    """
    计算单个餐厅的完整评分。

    user_tag_preferences: {tag_name: preference_score}，来自 user_profile
    weights: 动态权重字典，由 IntentAnalysis 传入（可选）。
        键：w_distance, w_price, w_rating, w_tag
        未提供时使用模块级默认值。
    penalty_factor: 乘法惩罚系数（0~1），用于松弛搜索中对边界外餐厅的降权。
        默认 1.0 表示不惩罚；松弛搜索时对预算溢出或品类泛化的餐厅降至 0.3~0.8。
    filter_budget_max: 原始硬筛选预算上限（元），用于软截断（soft-clipping）。
        当餐厅均价超出此值但在 10% 缓冲区内时，价格分线性衰减。
    """
    detail = ScoreDetail()

    # ── 距离分 ────────────────────────────────────────────────────────
    distance_m = restaurant.get("distance_m", 0) or 0
    max_dist = (req.max_distance or req.radius) or 2000
    detail.distance = max(0.0, 1.0 - distance_m / max_dist)

    # ── 价格分 ────────────────────────────────────────────────────────
    price = restaurant.get("avg_price", 0.0) or 0.0
    if price > 0 and req.budget_min is not None and req.budget_max is not None:
        mid_budget = (req.budget_min + req.budget_max) / 2.0
        tolerance = max(10.0, (req.budget_max - req.budget_min) / 2.0)
        detail.price = math.exp(-abs(price - mid_budget) / tolerance)
    else:
        detail.price = 0.5  # 中性分

    # ── 评分分 ────────────────────────────────────────────────────────
    rating = restaurant.get("rating", 0.0) or 0.0
    detail.rating = rating / 5.0 if rating > 0 else 0.4

    # ── 标签分 ────────────────────────────────────────────────────────
    category = restaurant.get("category", "") or ""
    restaurant_tags = get_tags(category)
    detail.matched_tags = []

    # 解析用户 taste（逗号分隔字符串或 None）
    user_tastes: list[str] = []
    if req.taste:
        user_tastes = [t.strip() for t in req.taste.split(",") if t.strip()]

    has_intent = len(user_tastes) > 0
    has_history = bool(user_tag_preferences)

    if not has_intent and not has_history:
        # 完全没有偏好信息：中性分，附上餐厅自带标签
        detail.tag = 0.5
        detail.matched_tags = restaurant_tags[:3] if restaurant_tags else []
    elif not restaurant_tags:
        # 餐厅无标签：无法匹配
        detail.tag = 0.0
    else:
        # 融合当下意图（user_tastes）和历史偏好（user_tag_preferences）
        # 构造餐厅标签→偏好权重映射
        combined_prefs: dict[str, float] = {}

        # 历史偏好作为基础（归一化到0~1）
        if has_history:
            alpha = 0.7 if has_intent else 0.0  # 有意图时历史占30%，否则历史占100%
            for tag, score in user_tag_preferences.items():
                combined_prefs[tag] = (1.0 - alpha) * score if has_intent else score

        # 当前意图叠加（权重 1.0）
        for taste in user_tastes:
            if has_history:
                combined_prefs[taste] = combined_prefs.get(taste, 0.0) + 0.7
            else:
                combined_prefs[taste] = 1.0

        # 计算匹配度：matched / max_possible
        matched_score = 0.0
        for rtag in restaurant_tags:
            if rtag in combined_prefs:
                matched_score += combined_prefs[rtag]
                detail.matched_tags.append(rtag)

        # 归一化：matched 占 combined_prefs 总权重的比例
        total_pref = sum(combined_prefs.values()) or 1.0
        detail.tag = min(1.0, matched_score / total_pref)

    # ── 价格软截断 (Soft-Clipping)：仅在松弛搜索时启用 ─────────────
    # 当提供了原始硬筛选预算上限且餐厅价格超出时，在缓冲区（0~10%）内线性衰减价格分
    if filter_budget_max is not None and price > 0:
        buffer_top = filter_budget_max * 1.10
        if price > filter_budget_max:
            if price <= buffer_top:
                # 缓冲区内：价格分线性从原始值衰减至 0.5
                overage_ratio = (price - filter_budget_max) / (filter_budget_max * 0.10)
                detail.price = detail.price * (1.0 - overage_ratio * 0.5)
            # 超出缓冲区的情况已由迭代松弛搜索剔除，此处不再处理

    # ── 最终综合评分 ──────────────────────────────────────────────────
    wd = (weights or {}).get("w_distance", W_DISTANCE)
    wp = (weights or {}).get("w_price",    W_PRICE)
    wr = (weights or {}).get("w_rating",   W_RATING)
    wt = (weights or {}).get("w_tag",      W_TAG)

    detail.final = (
        wd * detail.distance
        + wp * detail.price
        + wr * detail.rating
        + wt * detail.tag
    ) * penalty_factor  # 乘以惩罚系数（品类泛化/预算溢出时降权）

    return detail

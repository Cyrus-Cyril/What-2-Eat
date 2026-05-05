"""
app/services/explainer.py
生成结构化 explain 数据（ExplainData）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.services.scorer import ScoreDetail


@dataclass
class DimensionDetailLocal:
    dimension: str
    detail: str
    score_impact: Literal["high", "medium", "low"]


@dataclass
class ReasoningLogicLocal:
    primary_factor: str
    secondary_factor: str = ""


@dataclass
class ExplainData:
    scores: dict[str, float] = field(default_factory=dict)
    matched_tags: list[str] = field(default_factory=list)
    reason_hint: list[str] = field(default_factory=list)
    summary: str = ""
    reasoning_logic: ReasoningLogicLocal | None = None
    match_details: list[DimensionDetailLocal] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scores": self.scores,
            "matched_tags": self.matched_tags,
            "reason_hint": self.reason_hint,
            "summary": self.summary,
            "reasoning_logic": {
                "primary_factor": self.reasoning_logic.primary_factor,
                "secondary_factor": self.reasoning_logic.secondary_factor,
            } if self.reasoning_logic else None,
            "match_details": [
                {
                    "dimension": d.dimension,
                    "detail": d.detail,
                    "score_impact": d.score_impact,
                }
                for d in self.match_details
            ],
        }


def _score_impact(score: float) -> Literal["high", "medium", "low"]:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def build_explain(
    restaurant: dict,
    score_detail: ScoreDetail,
    taste: str | None = None,
) -> ExplainData:
    """
    根据评分明细生成 ExplainData，包含 dimension_details、reasoning_logic、summary。
    """
    hints: list[str] = []
    match_details: list[DimensionDetailLocal] = []

    distance_m = restaurant.get("distance_m", 0) or 0
    rating = restaurant.get("rating", 0.0) or 0.0
    avg_price = restaurant.get("avg_price", 0.0) or 0.0
    category = restaurant.get("category", "") or ""

    # ── 地理位置维度 ──────────────────────────────────────
    if distance_m <= 300:
        dist_detail = "步行5分钟内"
        hints.append("步行5分钟内")
    elif distance_m <= 800:
        dist_detail = "步行可达"
        hints.append("步行可达")
    else:
        dist_detail = f"距离约{distance_m}米"

    dist_impact = _score_impact(score_detail.distance)
    match_details.append(DimensionDetailLocal(
        dimension="地理位置",
        detail=dist_detail,
        score_impact=dist_impact,
    ))

    # ── 人均价格维度 ──────────────────────────────────────
    if score_detail.price >= 0.8:
        price_detail = f"人均约{int(avg_price)}元，非常合适"
        hints.append("价格非常合适")
    elif score_detail.price >= 0.6:
        price_detail = f"人均约{int(avg_price)}元，适中"
        hints.append("价格适中")
    else:
        price_detail = f"人均约{int(avg_price)}元，略超预算"

    price_impact = _score_impact(score_detail.price)
    match_details.append(DimensionDetailLocal(
        dimension="人均价格",
        detail=price_detail,
        score_impact=price_impact,
    ))

    # ── 用户口碑维度 ──────────────────────────────────────
    if rating >= 4.5:
        rating_detail = f"评分{rating:.1f}，口碑极佳"
        hints.append("口碑极佳")
    elif rating >= 4.0:
        rating_detail = f"评分{rating:.1f}，口碑较好"
        hints.append("评分较高")
    else:
        rating_detail = f"评分{rating:.1f}，口碑一般"

    rating_impact = _score_impact(score_detail.rating)
    match_details.append(DimensionDetailLocal(
        dimension="用户口碑",
        detail=rating_detail,
        score_impact=rating_impact,
    ))

    # ── 品类匹配维度 ──────────────────────────────────────
    if score_detail.matched_tags:
        tag_str = "、".join(score_detail.matched_tags[:2])
        tag_detail = f"完全符合「{tag_str}」口味"
        hints.append(tag_detail)
        tag_impact: Literal["high", "medium", "low"] = "high" if score_detail.tag >= 0.8 else "medium"
        match_details.append(DimensionDetailLocal(
            dimension="品类匹配",
            detail=tag_detail,
            score_impact=tag_impact,
        ))
    elif taste and score_detail.tag >= 0.5:
        hints.append("符合口味偏好")

    # ── reasoning_logic：取 score_impact 排名前两的维度 ──
    _impact_order = {"high": 2, "medium": 1, "low": 0}
    sorted_dims = sorted(match_details, key=lambda d: _impact_order[d.score_impact], reverse=True)

    reasoning_logic: ReasoningLogicLocal | None = None
    if sorted_dims:
        primary = sorted_dims[0]
        secondary = sorted_dims[1] if len(sorted_dims) > 1 else None
        reasoning_logic = ReasoningLogicLocal(
            primary_factor=f"{primary.dimension}：{primary.detail}",
            secondary_factor=f"{secondary.dimension}：{secondary.detail}" if secondary else "",
        )

    # ── summary ──────────────────────────────────────────
    category_short = category.split("/")[-1] if "/" in category else category
    if reasoning_logic:
        summary = f"{sorted_dims[0].detail}的{category_short}"
    else:
        summary = category_short

    reason_hint = hints[:3]

    return ExplainData(
        scores={
            "distance": round(score_detail.distance, 4),
            "price": round(score_detail.price, 4),
            "rating": round(score_detail.rating, 4),
            "tag": round(score_detail.tag, 4),
        },
        matched_tags=score_detail.matched_tags,
        reason_hint=reason_hint,
        summary=summary,
        reasoning_logic=reasoning_logic,
        match_details=match_details,
    )

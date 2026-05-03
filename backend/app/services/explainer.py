"""
app/services/explainer.py
生成结构化 explain 数据（ExplainData）
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.scorer import ScoreDetail


@dataclass
class ExplainData:
    scores: dict[str, float] = field(default_factory=dict)
    matched_tags: list[str] = field(default_factory=list)
    reason_hint: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scores": self.scores,
            "matched_tags": self.matched_tags,
            "reason_hint": self.reason_hint,
        }


def build_explain(
    restaurant: dict,
    score_detail: ScoreDetail,
    taste: str | None = None,
) -> ExplainData:
    """
    根据评分明细生成 ExplainData，reason_hint 最多取 3 条。
    """
    hints: list[str] = []

    distance_m = restaurant.get("distance_m", 0) or 0
    rating = restaurant.get("rating", 0.0) or 0.0

    # 距离提示
    if distance_m <= 300:
        hints.append("步行5分钟内")
    elif distance_m <= 800:
        hints.append("步行可达")

    # 评分提示
    if rating >= 4.5:
        hints.append("口碑极佳")
    elif rating >= 4.0:
        hints.append("评分较高")

    # 价格提示
    if score_detail.price >= 0.8:
        hints.append("价格非常合适")
    elif score_detail.price >= 0.6:
        hints.append("价格适中")

    # 标签/口味提示
    if score_detail.tag >= 0.8 and taste:
        display_taste = taste.replace(",", "、")
        hints.append(f"完全符合「{display_taste}」口味")
    elif score_detail.tag >= 0.5:
        hints.append("符合口味偏好")

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
    )

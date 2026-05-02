"""
app/services/recommender.py
推荐引擎 —— 基础阶段：负责调用数据入口 + 简单排序
后续阶段会在此模块中叠加反馈修正、分布式缓存查询等
"""
import logging

from app.services.data_entry import get_candidate_restaurants
from app.models.schemas import RecommendRequest, RecommendResponse, RestaurantOut

logger = logging.getLogger(__name__)


def recommend(req: RecommendRequest) -> RecommendResponse:

    logger.info(
        "收到推荐请求 user=%s lng=%.6f lat=%.6f radius=%d taste=%s budget=[%s,%s]",
        req.user_id, req.longitude, req.latitude, req.radius,
        req.taste, req.budget_min, req.budget_max,
    )

    try:
        raw_restaurants = get_candidate_restaurants(
            longitude=req.longitude,
            latitude=req.latitude,
            radius=req.radius,
            max_count=req.max_count,
        )
    except Exception as e:
        logger.exception("获取餐馆数据失败")
        return RecommendResponse(code=-1, message=f"数据获取异常: {str(e)}")

    if not raw_restaurants:
        return RecommendResponse(code=1, message="附近暂未找到餐馆，请扩大搜索范围")

    results: list[RestaurantOut] = []
    for r in raw_restaurants:
        score = _calc_score(r, req)
        reason = _build_reason(r, req, score)

        results.append(RestaurantOut(
            restaurant_id=r.get("restaurant_id", ""),
            name=r.get("name", ""),
            category=r.get("category", ""),
            distance_m=r.get("distance_m", 0),
            rating=r.get("rating", 0.0),
            avg_price=r.get("avg_price", 0.0),
            address=r.get("address", ""),
            latitude=r.get("latitude", 0.0),
            longitude=r.get("longitude", 0.0),
            score=round(score, 3),
            reason=reason,
        ))

    results.sort(key=lambda x: x.score, reverse=True)
    top_n = results[:req.max_count]

    logger.info("推荐完成 候选=%d 返回=%d", len(results), len(top_n))
    return RecommendResponse(code=0, data=top_n, total=len(top_n))


def _calc_score(r: dict, req: RecommendRequest) -> float:
    score = 0.0
    weight_sum = 0.0

    rating = r.get("rating", 0.0)
    if rating > 0:
        score += (rating / 5.0) * 0.30
        weight_sum += 0.30

    distance_m = r.get("distance_m", 0)
    max_dist = req.max_distance if req.max_distance else req.radius
    if max_dist and max_dist > 0:
        dist_factor = max(0, 1 - distance_m / max_dist)
        score += dist_factor * 0.30
        weight_sum += 0.30

    category = r.get("category", "")
    if req.taste and req.taste.strip():
        if req.taste in category or category in req.taste:
            score += 1.0 * 0.20
        weight_sum += 0.20

    price = r.get("avg_price", 0.0)
    if price > 0 and req.budget_min is not None and req.budget_max is not None:
        if req.budget_min <= price <= req.budget_max:
            score += 1.0 * 0.20
        elif price <= req.budget_max * 1.2:
            score += 0.5 * 0.20
        weight_sum += 0.20

    return score / weight_sum if weight_sum > 0 else score


def _build_reason(r: dict, req: RecommendRequest, score: float) -> str:
    parts = []

    distance_m = r.get("distance_m", 0)
    if distance_m <= 500:
        parts.append(f"距离仅{distance_m}m,非常近")
    elif distance_m <= 1000:
        parts.append(f"距离{distance_m}m,步行可达")

    rating = r.get("rating", 0.0)
    if rating >= 4.0:
        parts.append(f"评分{rating}分,口碑好")

    category = r.get("category", "")
    if req.taste and req.taste.strip() and req.taste in category:
        parts.append(f"符合你的「{req.taste}」口味偏好")

    price = r.get("avg_price", 0.0)
    if price > 0:
        parts.append(f"人均¥{price:.0f}")

    if not parts:
        parts.append("综合条件较匹配")

    return "；".join(parts)

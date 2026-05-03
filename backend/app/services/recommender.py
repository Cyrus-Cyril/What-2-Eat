"""
app/services/recommender.py
推荐引擎主流程 —— 接入 scorer / explainer / crud / tag_mapper
三层意图处理：
  Scene A (Context-Only)  — 无显式意图，按时间动态调整权重
  Scene B (Soft Boost)    — 模糊偏好，w_tag 提升 1.5x
  Scene C (Hard Filter)   — 明确品类/价格，先硬过滤候选集
"""
import asyncio
import logging

from app.services.data_entry import get_candidate_restaurants
from app.services.scorer import calc_all
from app.services.explainer import build_explain
from app.services.user_profile import get_user_profile
from app.services.tag_mapper import get_tags
from app.services.intent_parser import intent_parser
from app.models.schemas import RecommendRequest, RecommendResponse, RestaurantOut, ExplainData, ExplainScores

logger = logging.getLogger(__name__)


async def recommend_async(req: RecommendRequest) -> RecommendResponse:
    """推荐主流程（async）"""
    logger.info(
        "收到推荐请求 user=%s lng=%.4f lat=%.4f radius=%d taste=%s budget=[%s,%s]",
        req.user_id, req.longitude, req.latitude, req.radius,
        req.taste, req.budget_min, req.budget_max,
    )

    # Step 0: 意图分析 —— 获取过滤规则和动态权重
    intent = await intent_parser.analyze_intent(req.query)
    weights = {
        "w_distance": intent.w_distance,
        "w_price":    intent.w_price,
        "w_rating":   intent.w_rating,
        "w_tag":      intent.w_tag,
    }
    logger.info(
        "意图类型=%s filter_tags=%s boost_tags=%s filter_budget_max=%s "
        "weights=[D=%.2f P=%.2f R=%.2f T=%.2f]",
        intent.intent_type, intent.filter_tags, intent.boost_tags,
        intent.filter_budget_max,
        intent.w_distance, intent.w_price, intent.w_rating, intent.w_tag,
    )

    # Step 1: 获取用户历史偏好
    user_tag_prefs: dict = {}
    if req.user_id:
        profile = await get_user_profile(req.user_id)
        user_tag_prefs = profile.get("tag_preferences", {})

    # Step 2: 获取候选餐厅
    try:
        raw_restaurants = get_candidate_restaurants(
            longitude=req.longitude,
            latitude=req.latitude,
            radius=req.radius,
            max_count=req.max_count * 3,
        )
    except Exception as e:
        logger.exception("获取餐馆数据失败")
        return RecommendResponse(code=-1, message=f"数据获取异常: {str(e)}")

    if not raw_restaurants:
        return RecommendResponse(code=1, message="附近暂未找到餐馆，请扩大搜索范围")

    # Step 3: Scene C 硬过滤 —— 先剔除不符合标签或超出价格上限的候选
    if intent.intent_type == "hard_filter":
        filtered = _apply_hard_filter(raw_restaurants, intent.filter_tags, intent.filter_budget_max)
        if not filtered:
            # 硬过滤后无结果 → 交由 intent_parser 将硬约束降级为软增强权重
            intent = intent_parser.downgrade_to_soft_boost(intent)
            weights = {
                "w_distance": intent.w_distance,
                "w_price":    intent.w_price,
                "w_rating":   intent.w_rating,
                "w_tag":      intent.w_tag,
            }
        else:
            raw_restaurants = filtered
            logger.info("硬过滤：%d 条候选保留", len(filtered))

    # Step 4~5: 打分 + 生成 explain
    results: list[RestaurantOut] = []
    for r in raw_restaurants:
        score_detail = calc_all(r, req, user_tag_prefs, weights=weights)
        explain_obj = build_explain(r, score_detail, req.taste)
        reason = "；".join(explain_obj.reason_hint) if explain_obj.reason_hint else "综合条件较匹配"

        explain_pydantic = ExplainData(
            scores=ExplainScores(**explain_obj.scores),
            matched_tags=explain_obj.matched_tags,
            reason_hint=explain_obj.reason_hint,
        )

        results.append(RestaurantOut(
            restaurant_id=r.get("restaurant_id", ""),
            name=r.get("name", ""),
            category=r.get("category", ""),
            distance_m=int(r.get("distance_m", 0)),
            rating=float(r.get("rating", 0.0)),
            avg_price=float(r.get("avg_price", 0.0)),
            address=r.get("address", ""),
            latitude=float(r.get("latitude", 0.0)),
            longitude=float(r.get("longitude", 0.0)),
            score=round(score_detail.final, 4),
            reason=reason,
            explain=explain_pydantic,
        ))

    # Step 6: 排序 + 截取
    results.sort(key=lambda x: x.score, reverse=True)
    top_n = results[:req.max_count]

    # Step 7: 异步写库（不阻塞响应）
    if req.user_id:
        asyncio.ensure_future(_write_to_db(req, top_n))

    logger.info("推荐完成 候选=%d 返回=%d", len(results), len(top_n))
    return RecommendResponse(code=0, data=top_n, total=len(top_n))


def _apply_hard_filter(
    candidates: list[dict],
    filter_tags: list[str],
    filter_budget_max: float | None,
) -> list[dict]:
    """
    Scene C 硬过滤：
    - filter_tags 不为空时，保留餐厅标签与 filter_tags 有交集的候选
    - filter_budget_max 不为 None 时，排除均价超过上限的候选（均价为 0 视为未知，保留）
    """
    result = []
    for r in candidates:
        # 标签过滤
        if filter_tags:
            r_tags = get_tags(r.get("category", "") or "")
            if not any(ft in r_tags for ft in filter_tags):
                continue
        # 价格过滤
        if filter_budget_max is not None:
            avg_price = r.get("avg_price", 0) or 0
            if avg_price > 0 and avg_price > filter_budget_max:
                continue
        result.append(r)
    return result


async def _write_to_db(req: RecommendRequest, results: list[RestaurantOut]) -> None:
    try:
        from app.db.crud import save_query, save_recommendations
        query_id = await save_query(req)
        await save_recommendations(query_id, results)
    except Exception:
        logger.exception("写库失败，不影响主流程")



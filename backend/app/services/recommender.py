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
from app.services.explanation_builder import build_explanation_system, build_ai_speeches_for_top_n
from app.models.schemas import (
    RecommendRequest, RecommendResponse, RestaurantOut,
    ExplainData, ExplainScores, DimensionDetail, ReasoningLogic,
)

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
    # 因为现在并没有用户模型，所以这一部分依旧待定
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
    # 说明：
    # - 对每个候选餐厅执行完整评分（calc_all），得到各维度分数与最终综合分
    # - 基于评分明细使用规则引擎生成局部解释对象（build_explain），该对象为库内 dataclass，包含
    #   dimension_details、reasoning_logic、summary 等结构化字段（供 LLM 或前端展示使用）
    # - 将局部解释从内部 dataclass 转换为 Pydantic 模型（ExplainData），以便后续统一序列化与注入
    # - 同时拼接简短 reason 文本（用于内部日志或存库的简要说明），但不会作为最终对外的完整解释
    results: list[RestaurantOut] = []

    for r in raw_restaurants:
        # 1) 计算评分明细。返回 ScoreDetail，包含 distance/price/rating/tag/final 等字段
        score_detail = calc_all(r, req, user_tag_prefs, weights=weights)

        # 2) 基于评分明细生成结构化解释（规则层）
        #    该函数返回本模块内部的 ExplainData dataclass（不是 Pydantic），包含用于生成自然语言的证据链
        explain_obj = build_explain(r, score_detail, req.taste)

        # 3) 生成简短的合成理由（用于表格列或数据库的 reason 字段），最多取 3 条 hint
        reason = "；".join(explain_obj.reason_hint) if explain_obj.reason_hint else "综合条件较匹配"

        # 4) 将内部 explain dataclass 的子结构转换为 Pydantic 类型，便于后续序列化与校验：
        #    - DimensionDetail: 单维度解释（dimension/detail/score_impact）
        #    - ReasoningLogic: primary/secondary 两个关键因素
        #
        #    注意：这里仍保留 ExplainData 中的 scores/matched_tags/reason_hint 字段，
        #    这些字段仅用于后端内部逻辑或 LLM prompt 构造，后续在返回给前端时会选择性剥离。
        dim_details_pydantic = [
            DimensionDetail(
                dimension=d.dimension,
                detail=d.detail,
                score_impact=d.score_impact,
            )
            for d in explain_obj.dimension_details
        ]

        rl = explain_obj.reasoning_logic
        reasoning_logic_pydantic = (
            ReasoningLogic(
                primary_factor=rl.primary_factor,
                secondary_factor=rl.secondary_factor,
            )
            if rl else None
        )

        # 5) 将完整的 ExplainData 拼装为 Pydantic 实例（用于内部流转与可选存储）
        explain_pydantic = ExplainData(
            scores=ExplainScores(**explain_obj.scores),
            matched_tags=explain_obj.matched_tags,
            reason_hint=explain_obj.reason_hint,
            summary=explain_obj.summary or None,
            reasoning_logic=reasoning_logic_pydantic,
            dimension_details=dim_details_pydantic,
        )

        # 6) 将打分与解释注入到内部返回对象 RestaurantOut（包含完整数据，供内部使用与写库）
        #    说明：RestaurantOut 是内部使用的 Pydantic 模型，包含 score、explain 等字段。
        #    在最终对外返回时，会把 RestaurantOut 映射为更小的前端视图 RecommendationItem，
        #    以避免将内部敏感或冗余的信息暴露给前端（例如 raw scores、matched_tags、reason_hint）。
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

    # Step 7: 并发生成全局解释系统 + 各餐厅 ai_speech
    speech_inputs = [
        {
            "name": r.name,
            "dimension_details": r.explain.dimension_details if r.explain else [],
            "reasoning_logic": r.explain.reasoning_logic if r.explain else None,
        }
        for r in top_n
    ]

    explanation_system, ai_speeches = await asyncio.gather(
        build_explanation_system(intent, req.query, len(top_n)),
        build_ai_speeches_for_top_n(speech_inputs),
    )

    # 将 ai_speech 注入各餐厅 explain
    for restaurant, speech in zip(top_n, ai_speeches):
        if restaurant.explain is not None and speech:
            restaurant.explain.ai_speech = speech

    # Step 8: 异步写库（不阻塞响应）
    if req.user_id:
        asyncio.ensure_future(_write_to_db(req, top_n))

    logger.info("推荐完成 候选=%d 返回=%d", len(results), len(top_n))
    return RecommendResponse(
        code=0,
        data=top_n,
        total=len(top_n),
        explanation_system=explanation_system,
    )


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



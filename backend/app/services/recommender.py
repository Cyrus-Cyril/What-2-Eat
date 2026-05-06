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
from app.services.tag_mapper import get_tags, get_parent_tags
from app.services.intent_parser import intent_parser
from app.services.explanation_builder import build_explanation_system, build_ai_speeches_for_top_n
from app.models.schemas import (
    RecommendRequest, RecommendResponse, RestaurantOut,
    ExplainData, ExplainScores, DimensionDetail, ReasoningLogic,
    ExplanationOut, RecommendationItem,
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

    # Step 3: Scene C 迭代松弛搜索
    # 替换原来的"一刀切"硬过滤，采用四步迭代策略：
    #   Step 1 严格匹配 → Step 2 预算浮动+20% → Step 3 品类语义泛化 → Step 4 完全降级
    # 同时返回 relaxation_info（记录本次搜索策略），传入解释系统生成 my_logic 字段
    relaxation_info: dict = {}
    if intent.intent_type == "hard_filter":
        raw_restaurants, relaxation_info, intent = _iterative_relaxation_search(
            raw_restaurants, intent, min_count=3
        )
        weights = {
            "w_distance": intent.w_distance,
            "w_price":    intent.w_price,
            "w_rating":   intent.w_rating,
            "w_tag":      intent.w_tag,
        }

    # Step 4~5: 打分 + 生成 explain
    # 说明：
    # - 对每个候选餐厅执行完整评分（calc_all），得到各维度分数与最终综合分
    # - 基于评分明细使用规则引擎生成局部解释对象（build_explain），该对象为库内 dataclass，包含
    #   dimension_details、reasoning_logic、summary 等结构化字段（供 LLM 或前端展示使用）
    # - 将局部解释从内部 dataclass 转换为 Pydantic 模型（ExplainData），以便后续统一序列化与注入
    # - 同时拼接简短 reason 文本（用于内部日志或存库的简要说明），但不会作为最终对外的完整解释
    results: list[RestaurantOut] = []

    for r in raw_restaurants:
        # 计算本餐厅在松弛搜索中的惩罚系数：
        #   - level 1（预算浮动）：超出原始预算上限的餐厅乘以 0.7
        #   - level 2（品类泛化）：仅命中父级标签（非原始标签）的餐厅乘以 0.3
        penalty_factor = 1.0
        orig_budget = relaxation_info.get("original_budget_max")
        orig_tags = relaxation_info.get("original_filter_tags", [])

        if relaxation_info.get("budget_relaxed") and orig_budget is not None:
            price = r.get("avg_price", 0) or 0
            if price > orig_budget:
                # 缓冲区内线性惩罚：溢出越多，惩罚越重（最低 0.5）
                overage_ratio = min(1.0, (price - orig_budget) / (orig_budget * 0.20))
                penalty_factor *= max(0.5, 1.0 - overage_ratio * 0.5)

        if relaxation_info.get("tags_generalized") and orig_tags:
            r_tags = get_tags(r.get("category", "") or "")
            if not any(ft in r_tags for ft in orig_tags):
                # 品类仅为泛化匹配（非精确命中），强惩罚确保其排名低于精确匹配
                penalty_factor *= 0.3

        # 1) 计算评分明细（含 penalty_factor 和 soft-clipping 参数）
        score_detail = calc_all(
            r, req, user_tag_prefs,
            weights=weights,
            penalty_factor=penalty_factor,
            filter_budget_max=orig_budget,
        )

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
            for d in explain_obj.match_details
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
            match_details=dim_details_pydantic,
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
            "match_details": r.explain.match_details if r.explain else [],
            "reasoning_logic": r.explain.reasoning_logic if r.explain else None,
        }
        for r in top_n
    ]

    explanation_system, ai_speeches = await asyncio.gather(
        build_explanation_system(intent, req.query, len(top_n), relaxation_info),
        build_ai_speeches_for_top_n(speech_inputs),
    )

    # 将 ai_speech 注入各餐厅 explain
    for restaurant, speech in zip(top_n, ai_speeches):
        if restaurant.explain is not None and speech:
            restaurant.explain.ai_speech = speech

    # Step 8: 异步写库（不阻塞响应）
    if req.user_id:
        asyncio.ensure_future(_write_to_db(req, top_n))

    # Step 9: 将内部 RestaurantOut 映射为前端公开的 RecommendationItem（剥离内部字段）
    recommendation_items = [
        RecommendationItem(
            restaurant_id=r.restaurant_id,
            restaurant_name=r.name,
            explanation=ExplanationOut(
                summary=r.explain.summary if r.explain else None,
                reasoning_logic=r.explain.reasoning_logic if r.explain else None,
                match_details=r.explain.match_details if r.explain else [],
                ai_speech=r.explain.ai_speech if r.explain else None,
            ) if r.explain else None,
        )
        for r in top_n
    ]

    logger.info("推荐完成 候选=%d 返回=%d", len(results), len(top_n))
    return RecommendResponse(
        code=0,
        explanation_system=explanation_system,
        recommendations=recommendation_items,
    )


def _apply_filter(
    candidates: list[dict],
    filter_tags: list[str],
    budget_max: float | None,
) -> list[dict]:
    """
    基础过滤器：按标签列表（有交集即保留）和预算上限过滤候选餐厅。
    """
    result = []
    for r in candidates:
        if filter_tags:
            r_tags = get_tags(r.get("category", "") or "")
            if not any(ft in r_tags for ft in filter_tags):
                continue
        if budget_max is not None:
            avg_price = r.get("avg_price", 0) or 0
            if avg_price > 0 and avg_price > budget_max:
                continue
        result.append(r)
    return result


def _iterative_relaxation_search(
    raw_restaurants: list[dict],
    intent,
    min_count: int = 3,
) -> tuple[list[dict], dict, object]:
    """
    迭代松弛搜索（Scene C 专用）：
      Step 1 - 严格匹配：全部 filter_tags + filter_budget_max
      Step 2 - 预算浮动：保持品类，预算上限 +20%
      Step 3 - 语义泛化：品类扩展到父级（如 火锅→川菜/中餐）
      Step 4 - 完全降级：调用 downgrade_to_soft_boost，转为软增强

    返回：(候选餐厅列表, relaxation_info, 更新后的 intent)
    relaxation_info 包含本次策略摘要，用于生成 my_logic 和 hello_voice 坦白告知。
    """
    filter_tags = intent.filter_tags[:]
    budget_max = intent.filter_budget_max

    relaxation_info: dict = {
        "level": 0,
        "original_filter_tags": filter_tags[:],
        "original_budget_max": budget_max,
        "budget_relaxed": False,
        "tags_generalized": False,
        "downgraded": False,
        "note": "严格匹配所有条件",
    }

    # Step 1: 严格匹配
    candidates = _apply_filter(raw_restaurants, filter_tags, budget_max)
    logger.info("松弛搜索 Step 1 严格匹配：%d 条", len(candidates))
    if len(candidates) >= min_count:
        return candidates, relaxation_info, intent

    # Step 2: 预算浮动 +20%
    if budget_max is not None:
        relaxed_budget = round(budget_max * 1.20, 1)
        candidates = _apply_filter(raw_restaurants, filter_tags, relaxed_budget)
        logger.info("松弛搜索 Step 2 预算浮动 %.0f→%.0f：%d 条", budget_max, relaxed_budget, len(candidates))
        if len(candidates) >= min_count:
            relaxation_info.update({
                "level": 1,
                "budget_relaxed": True,
                "relaxed_budget_max": relaxed_budget,
                "note": f"预算从{int(budget_max)}元放宽至{int(relaxed_budget)}元（+20%），稍微贵了一点点",
            })
            return candidates, relaxation_info, intent

    # Step 3: 语义泛化（品类扩展到父级标签）
    if filter_tags:
        parent_tags = get_parent_tags(filter_tags)
        if parent_tags:
            candidates = _apply_filter(raw_restaurants, parent_tags, budget_max)
            logger.info("松弛搜索 Step 3 品类泛化 %s→%s：%d 条", filter_tags, parent_tags, len(candidates))
            if len(candidates) >= min_count:
                relaxation_info.update({
                    "level": 2,
                    "tags_generalized": True,
                    "generalized_tags": parent_tags,
                    "note": f"附近「{'、'.join(filter_tags)}」太少了，帮你扩展到了「{'、'.join(parent_tags)}」",
                })
                return candidates, relaxation_info, intent

    # Step 4: 完全降级为 soft_boost
    intent = intent_parser.downgrade_to_soft_boost(intent)
    relaxation_info.update({
        "level": 3,
        "downgraded": True,
        "note": "附近实在没有完全符合的，已切换为偏好推荐模式",
    })
    logger.info("松弛搜索 Step 4 完全降级，返回全部候选")
    return raw_restaurants, relaxation_info, intent


async def _write_to_db(req: RecommendRequest, results: list[RestaurantOut]) -> None:
    try:
        from app.db.crud import save_query, save_recommendations
        query_id = await save_query(req)
        await save_recommendations(query_id, results)
    except Exception:
        logger.exception("写库失败，不影响主流程")



"""
app/services/recommender.py
推荐引擎主流程 —— 接入 scorer / explainer / crud / tag_mapper
弹性约束模型（三层解析架构）：
  - 意图解析产出 IntentConstraint（维度/强度/权重）
  - PenaltyCalculator 按强度施加惩罚（required→S型曲线，preferred→指数衰减）
  - FinalScore = (Σ w_intent * Score_dim) × Π Penalty_dim
  - 兜底：Top-N 全部 < FALLBACK_THRESHOLD 时，降级 required→preferred 重新打分
"""
import asyncio
import logging
import math
import json
from dataclasses import asdict

from app.services.data_entry import get_candidate_restaurants
from app.services.scorer import calc_all
from app.services.explainer import build_explain
from app.services.user_profile import get_user_profile
from app.services.tag_mapper import get_tags
from app.services.intent_parser import intent_parser, IntentConstraint, ConstraintItem
from app.services.explanation_builder import build_explanation_system, build_ai_speeches_for_top_n
from app.db.crud import get_user_blacklist, get_recent_feedback_context
from app.models.schemas import (
    RecommendRequest, RecommendResponse, RestaurantOut,
    ExplainData, ExplainScores, DimensionDetail, ReasoningLogic,
    ExplanationOut, RecommendationItem,
)

logger = logging.getLogger(__name__)

# 兜底触发阈值：Top-N 全部低于此值时触发 required→preferred 降级
_FALLBACK_THRESHOLD = 0.1


class PenaltyCalculator:
    """
    弹性约束惩罚计算器。
    根据约束强度（strength）选择惩罚曲线：
      required  → 陡峭 S 型曲线（超一点点，分数断崖式下跌）
      preferred → 平缓指数衰减（容忍度由 tolerance 控制）
      neutral   → 无惩罚（返回 1.0）
    """

    @staticmethod
    def s_curve_penalty(violation_ratio: float) -> float:
        """
        陡峭 S 型曲线惩罚（required 强度专用）。
        violation_ratio: 0=恰好满足, 1=超出100%；超出 10% 时开始急剧下降。
        """
        k = 15.0    # 曲线陡峭程度
        x0 = 0.10   # 转折点（超出10%开始急降）
        return 1.0 / (1.0 + math.exp(k * (violation_ratio - x0)))

    @staticmethod
    def exp_decay_penalty(violation_ratio: float, tolerance: str | None = None) -> float:
        """
        平缓指数衰减（preferred 强度专用）。
        tolerance: "high"→衰减慢, "medium"→默认, "low"→衰减快
        """
        lambda_map = {"high": 1.0, "medium": 2.0, "low": 3.0}
        lam = lambda_map.get(tolerance or "medium", 2.0)
        return math.exp(-lam * max(0.0, violation_ratio))

    @classmethod
    def compute(
        cls,
        dim: str,
        constraint: ConstraintItem,
        restaurant: dict,
        req: RecommendRequest,
    ) -> float:
        """计算单维度惩罚系数（0~1，1 表示不惩罚）"""
        strength = constraint.strength
        if strength == "neutral":
            return 1.0

        if dim == "tags":
            required_tags = constraint.values
            if not required_tags:
                return 1.0
            r_tags = get_tags(restaurant.get("category", "") or "")
            # 命中率：matched / total_required
            hit = sum(1 for t in required_tags if t in r_tags) / len(required_tags)
            violation = 1.0 - hit  # 0=全命中, 1=全未命中
            if strength == "required":
                return cls.s_curve_penalty(violation)
            return cls.exp_decay_penalty(violation)

        if dim == "price":
            price = restaurant.get("avg_price", 0) or 0
            if price <= 0:
                return 1.0
            ref = constraint.max_limit or constraint.preferred
            if not ref or ref <= 0:
                return 1.0
            if price <= ref:
                return 1.0
            violation_ratio = (price - ref) / ref
            if strength == "required":
                return cls.s_curve_penalty(violation_ratio)
            return cls.exp_decay_penalty(violation_ratio, constraint.tolerance)

        if dim == "distance":
            distance_m = restaurant.get("distance_m", 0) or 0
            limit = constraint.max_limit
            if not limit or limit <= 0:
                return 1.0
            if distance_m <= limit:
                return 1.0
            violation_ratio = (distance_m - limit) / limit
            if strength == "required":
                return cls.s_curve_penalty(violation_ratio)
            return cls.exp_decay_penalty(violation_ratio)

        # rating 维度通过基础 RatingScore 已体现，不另施惩罚
        return 1.0


def _build_weights(intent: IntentConstraint) -> dict[str, float]:
    """从 IntentConstraint 中提取各维度权重，映射为 calc_all 所需的 w_xxx 格式"""
    c = intent.constraints
    return {
        "w_distance": c.get("distance", ConstraintItem()).weight,
        "w_price":    c.get("price",    ConstraintItem()).weight,
        "w_rating":   c.get("rating",   ConstraintItem()).weight,
        "w_tag":      c.get("tags",     ConstraintItem()).weight,
    }


def _score_restaurants(
    candidates: list[dict],
    req: RecommendRequest,
    intent: IntentConstraint,
    user_tag_prefs: dict,
) -> list[RestaurantOut]:
    """
    对候选餐厅完整打分（含约束惩罚），返回 RestaurantOut 列表。
    公式：FinalScore = (Σ w_intent * Score_dim) × Π Penalty_dim
    """
    weights = _build_weights(intent)
    results: list[RestaurantOut] = []

    for r in candidates:
        # 1) 计算各维度约束惩罚（乘法累积）
        penalty = 1.0
        for dim, constraint_item in intent.constraints.items():
            penalty *= PenaltyCalculator.compute(dim, constraint_item, r, req)

        # 2) 计算基础评分明细
        score_detail = calc_all(r, req, user_tag_prefs, weights=weights)

        # 3) 将惩罚乘入最终分（替代旧的 penalty_factor 参数）
        score_detail.final = round(score_detail.final * penalty, 4)

        # 4) 规则引擎生成结构化解释
        explain_obj = build_explain(r, score_detail, req.taste, budget_max=req.budget_max)
        reason = "；".join(explain_obj.reason_hint) if explain_obj.reason_hint else "综合条件较匹配"

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
        explain_pydantic = ExplainData(
            scores=ExplainScores(**explain_obj.scores),
            matched_tags=explain_obj.matched_tags,
            reason_hint=explain_obj.reason_hint,
            summary=explain_obj.summary or None,
            reasoning_logic=reasoning_logic_pydantic,
            match_details=dim_details_pydantic,
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
            score=score_detail.final,
            reason=reason,
            explain=explain_pydantic,
        ))

    return results


async def recommend_async(req: RecommendRequest) -> RecommendResponse:
    """推荐主流程（async）"""
    logger.info(
        "收到推荐请求 user=%s lng=%.4f lat=%.4f radius=%d taste=%s budget=[%s,%s]",
        req.user_id, req.longitude, req.latitude, req.radius,
        req.taste, req.budget_min, req.budget_max,
    )

    # Step 0: 意图分析 —— 优先使用 parse() 预置的 IntentConstraint（零额外 LLM 调用）
    intent: IntentConstraint = (
        req.intent
        if isinstance(req.intent, IntentConstraint)
        else await intent_parser.analyze_intent(req.query)
    )
    # 将 dataclass 转为可读 JSON 结构打印（保留中文）
    try:
        intent_dict = asdict(intent)
        logger.info("意图解析结果:\n%s", json.dumps(intent_dict, ensure_ascii=False, indent=2))
    except Exception:
        logger.info("意图解析结果: %s", intent)

    # Step 1: 用户历史偏好 + 黑名单 + 反馈上下文
    user_tag_prefs: dict = {}
    blacklist: set[str] = set()
    recent_feedback_context: dict = {}
    if req.user_id:
        profile = await get_user_profile(req.user_id)
        user_tag_prefs = profile.get("tag_preferences", {})
        blacklist = set(await get_user_blacklist(req.user_id, hours=24))
        recent_feedback_context = await get_recent_feedback_context(req.user_id)
        if blacklist:
            logger.info("黑名单过滤 user=%s count=%d", req.user_id, len(blacklist))

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

    # Step 3: 黑名单过滤 + exclude_tags 硬排除（用户明确说"不要"的品类）
    if blacklist:
        raw_restaurants = [r for r in raw_restaurants if r.get("restaurant_id", "") not in blacklist]

    if intent.exclude_tags:
        raw_restaurants = [
            r for r in raw_restaurants
            if not any(et in get_tags(r.get("category", "") or "") for et in intent.exclude_tags)
        ]
        logger.info("exclude_tags 排除后剩余候选：%d", len(raw_restaurants))

    if not raw_restaurants:
        return RecommendResponse(code=1, message="附近餐馆已被您排除，请调整筛选条件或稍后再试")

    # Step 4: 打分（含约束惩罚）
    results = _score_restaurants(raw_restaurants, req, intent, user_tag_prefs)
    results.sort(key=lambda x: x.score, reverse=True)
    top_n = results[:req.max_count] if req.max_count else results[:3]

    # Step 5: 兜底保底逻辑 —— Top-N 全部 < FALLBACK_THRESHOLD 时，松弛 required→preferred
    fallback_note: str = ""
    if top_n and all(r.score < _FALLBACK_THRESHOLD for r in top_n):
        logger.info(
            "兜底触发：Top-%d 分数均 < %.2f，降级 required→preferred 重新打分",
            len(top_n), _FALLBACK_THRESHOLD,
        )
        intent = intent_parser.relax_to_preferred(intent)
        results = _score_restaurants(raw_restaurants, req, intent, user_tag_prefs)
        results.sort(key=lambda x: x.score, reverse=True)
        top_n = results[:req.max_count] if req.max_count else results[:3]
        fallback_note = "附近暂时没有完全符合要求的餐厅，已自动放宽限制重新推荐"

    # Step 6: 并发生成全局解释 + 各餐厅 ai_speech
    speech_inputs = [
        {
            "name": r.name,
            "match_details": r.explain.match_details if r.explain else [],
            "reasoning_logic": r.explain.reasoning_logic if r.explain else None,
        }
        for r in top_n
    ]
    explanation_system, ai_speeches = await asyncio.gather(
        build_explanation_system(
            intent, req.query, len(top_n),
            fallback_note=fallback_note,
            recent_feedback_context=recent_feedback_context,
        ),
        build_ai_speeches_for_top_n(speech_inputs),
    )

    # Step 7: 注入 ai_speech
    for restaurant, speech in zip(top_n, ai_speeches):
        if restaurant.explain is not None and speech:
            restaurant.explain.ai_speech = speech

    # Step 8: 异步写库（不阻塞响应）
    if req.user_id:
        asyncio.ensure_future(_write_to_db(req, top_n))

    # Step 9: 映射为前端公开的 RecommendationItem
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


async def _write_to_db(req: RecommendRequest, results: list[RestaurantOut]) -> None:
    try:
        from app.db.crud import save_query, save_recommendations
        query_id = await save_query(req)
        await save_recommendations(query_id, results)
    except Exception:
        logger.exception("写库失败，不影响主流程")


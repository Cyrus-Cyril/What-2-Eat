"""
app/api/routes.py
API 路由 —— 所有前后端交互接口的入口
"""
import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Query

from app.models.schemas import (
    RecommendRequest, RecommendResponse,
    FeedbackRequest, FeedbackResponse,
    HistoryResponse, HistoryItem,
    HealthResponse,
    NearbyRequest, NearbyResponse, NearbyRestaurantItem,
    PresetRecommendRequest, PresetRecommendResponse,
    ParseIntentResponse, ParsedIntentResult, AnalysisStep,
)
from app.services.intent_parser import intent_parser, IntentParser
from app.services.recommender import recommend_async
from app.services.preset_recommender import recommend_by_preset
from app.services.user_profile import update_preference_from_feedback
from app.db.crud import save_feedback, save_interaction, get_history

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse, tags=["系统"])
def health_check():
    return HealthResponse(status="ok", version="0.2.0")


@router.post("/nearby", response_model=NearbyResponse, tags=["预取"])
async def prefetch_nearby(req: NearbyRequest):
    """
    周边餐厅预取接口。
    在用户尚未发起推荐请求时，由前端提前调用，传入当前经纬度，
    后端从高德 API 拉取附近餐厅数据并写入 Redis + 数据库，
    从而让后续推荐请求直接命中缓存，提升响应速度。

    - 数据会写入 Redis（TTL=600s）供推荐引擎高速读取
    - 同时 upsert 到 MySQL 供离线查询与缓存过期后的 DB 回源
    - 返回获取到的餐厅列表，供前端展示"周边餐厅一览"
    """
    from app.services.data_entry import prefetch_and_store

    logger.info(
        "预取请求 lng=%.4f lat=%.4f radius=%d max=%d",
        req.longitude, req.latitude, req.radius, req.max_count,
    )
    restaurants = await prefetch_and_store(
        longitude=req.longitude,
        latitude=req.latitude,
        radius=req.radius,
        max_count=req.max_count,
    )

    if not restaurants:
        return NearbyResponse(code=1, message="附近暂未找到餐厅，请稍后重试", count=0, source="api")

    items = [
        NearbyRestaurantItem(
            restaurant_id=r["restaurant_id"],
            name=r["name"],
            category=r.get("category", ""),
            distance_m=int(r.get("distance_m", 0)),
            rating=float(r.get("rating", 0.0)),
            avg_price=float(r.get("avg_price", 0.0)),
            address=r.get("address", ""),
            latitude=float(r.get("latitude", 0.0)),
            longitude=float(r.get("longitude", 0.0)),
        )
        for r in restaurants
    ]
    return NearbyResponse(
        code=0,
        message="ok",
        count=len(items),
        source="api",
        restaurants=items,
    )


@router.post("/recommend", response_model=RecommendResponse, tags=["推荐"])
async def get_recommendation(req: RecommendRequest):
    # 极速模式：完全跳过 LLM，直接用默认中性约束
    if req.fast_mode:
        req.intent = IntentParser._default_neutral_constraint()
    elif req.query and req.query.strip():
        req = await intent_parser.parse(
            user_id=req.user_id,
            query=req.query,
            raw_params=req.model_dump()
        )
    return await recommend_async(req)


@router.post("/parse-intent", response_model=ParseIntentResponse, tags=["推荐"])
async def parse_intent_endpoint(req: RecommendRequest):
    """
    单独的意图解析接口。供前端在"帮我选吃的"阶段展示解析动画。

    核心逻辑：调用真实 LLM 进行意图解析，然后将 LLM 结果与前端传来的
    表单参数（taste / budget / people_count）合并，得到最终的综合解析结果。
    LLM 调用内部做了缓存，后续 /api/recommend 会直接命中缓存。
    """
    # ── 1. 调用 LLM（有 query 时）───────────────────────────────
    raw = {}
    if req.query and req.query.strip() and not req.fast_mode:
        raw = await intent_parser._call_unified_llm(req.query)

    # ── 2. 合并 LLM 与前端参数 ──────────────────────────────────
    # 场景：LLM 推断 > 默认
    scene = raw.get("scene") or "日常就餐"

    # 人数：前端表单选择为权威来源
    people_count = f"{req.people_count}人" if req.people_count else "未知人数"

    # 预算：前端 budget_max 优先（有实际选择时），否则用 LLM 推断，再否则"不限"
    budget_max = req.budget_max or raw.get("budget_max")
    budget = f"{budget_max}元以内" if budget_max else "不限"

    # 口味：LLM taste + 前端 taste 合并去重
    llm_tastes = raw.get("taste") or []
    if not isinstance(llm_tastes, list):
        llm_tastes = [llm_tastes] if llm_tastes else []
    frontend_taste = req.taste
    if frontend_taste:
        # req.taste 可能是逗号分隔的字符串（如 "火锅,川菜"）
        if isinstance(frontend_taste, str):
            frontend_tastes = [t.strip() for t in frontend_taste.split(",") if t.strip()]
        else:
            frontend_tastes = [frontend_taste]
        llm_tastes = [t for t in llm_tastes if t] + [t for t in frontend_tastes if t]
        # 保序去重
        seen = set()
        all_tastes = []
        for t in llm_tastes:
            if t and t not in seen:
                seen.add(t)
                all_tastes.append(t)
        llm_tastes = all_tastes
    taste_str = "、".join(llm_tastes) if llm_tastes else "不限"

    # 需求：LLM reason_hint 为主要来源
    needs = raw.get("reason_hint") or "无特殊需求"

    # ── 3. 优先使用 LLM 返回的 analysis_steps（已由 LLM 融合推断）──
    # 但人数 / 预算需要覆盖为前端表单的权威值
    raw_steps = raw.get("analysis_steps") if raw else None
    if raw_steps and isinstance(raw_steps, list) and len(raw_steps) == 5:
        # LLM 返回了 steps：保持 label，但人数/预算用合并后的值覆盖
        merged_steps = []
        for s in raw_steps:
            label = s.get("label", "")
            value = s.get("value", "")
            if "人数" in label:
                value = people_count
            elif "预算" in label:
                value = budget
            elif "口味" in label:
                value = taste_str
            merged_steps.append(AnalysisStep(label=label, value=value))
        analysis_steps = merged_steps
    else:
        # LLM 未返回 steps：由合并后的结果自行构造
        analysis_steps = [
            AnalysisStep(label="就餐场景", value=scene),
            AnalysisStep(label="人数", value=people_count),
            AnalysisStep(label="预算", value=budget),
            AnalysisStep(label="口味偏好", value=taste_str),
            AnalysisStep(label="需求", value=needs),
        ]

    # ── 4. 返回合并后的最终结果 ─────────────────────────────────
    parsed = ParsedIntentResult(
        scene=scene,
        people_count=people_count,
        budget=budget,
        taste=taste_str,
        needs=needs,
        analysis_steps=analysis_steps,
    )
    return ParseIntentResponse(code=0, message="ok", parsed=parsed)


@router.post("/preset-recommend", response_model=PresetRecommendResponse, tags=["推荐"])
async def get_preset_recommendation(req: PresetRecommendRequest):
    """
    预设偏好推荐接口 —— 不调用 LLM，基于用户预设标签直接从高德 API 获取数据并评分。

    适用场景：首页右侧"偏好推荐"卡片轮播。

    与 /api/recommend 的区别：
      - 不经过自然语言意图解析（无 LLM 调用）
      - 使用独立的固定权重评分公式
      - 直接基于用户 profile 中的偏好标签、预算、距离等参数
    """
    import config as _cfg

    recommendations = await recommend_by_preset(req)

    if not recommendations:
        return PresetRecommendResponse(code=1, message="附近暂未找到匹配你偏好的餐厅，请稍后重试")

    source = "mock" if _cfg.USE_MOCK else "api"
    return PresetRecommendResponse(
        code=0,
        message="ok",
        source=source,
        recommendations=recommendations,
    )


@router.get("/speeches/{result_id}", tags=["推荐"])
async def get_speeches(result_id: str):
    """
    轮询接口：获取后台异步生成的 ai_speech 列表。
    推荐接口返回 result_id 后，前端每 1.5s 轮询一次，最多轮询 6 次。
    code=0 且 speeches 非空表示已就绪；code=1 表示尚未就绪。
    """
    from app.db.redis_client import redis_client as _rc
    if not _rc:
        return {"code": 1, "message": "缓存不可用", "speeches": []}
    try:
        data = await asyncio.to_thread(_rc.get, f"speeches:{result_id}")
        if not data:
            return {"code": 1, "message": "尚未就绪", "speeches": []}
        return {"code": 0, "speeches": json.loads(data)}
    except Exception:
        logger.exception("读取 speeches 失败 result_id=%s", result_id)
        return {"code": 1, "message": "读取失败", "speeches": []}


@router.post("/feedback", response_model=FeedbackResponse, tags=["反馈"])
async def submit_feedback(req: FeedbackRequest, background_tasks: BackgroundTasks):
    # 从 action_type 或 rating 推导最终 action
    action_type = req.action_type
    if action_type is None:
        if req.rating >= 4:
            action_type = "LIKE"
        elif req.rating <= 2:
            action_type = "DISLIKE"

    logger.info(
        "收到反馈 user=%s restaurant=%s action=%s rating=%d chosen=%s",
        req.user_id, req.restaurant_id, action_type, req.rating, req.chosen,
    )

    # 立即写反馈表（同步，轻量）
    await save_feedback(
        user_id=req.user_id,
        recommendation_id=req.recommendation_id,
        restaurant_id=req.restaurant_id,
        rating=req.rating,
        chosen=req.chosen,
    )

    # 写 interaction 表（显式表态记录，用于黑名单查询）
    if action_type in ("LIKE", "DISLIKE"):
        await save_interaction(req.user_id, req.restaurant_id, action_type)

    # 偏好更新：异步后台执行，不阻塞响应
    if action_type in ("LIKE", "DISLIKE"):
        background_tasks.add_task(
            update_preference_from_feedback,
            req.user_id,
            req.restaurant_id,
            action_type,
        )

    return FeedbackResponse(code=0, message="反馈已记录")


@router.get("/history", response_model=HistoryResponse, tags=["历史"])
async def get_history_records(
    user_id: str = Query(description="用户标识"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
):
    logger.info("查询历史 user=%s page=%d size=%d", user_id, page, page_size)
    items, total = await get_history(user_id, page, page_size)
    history_items = [HistoryItem(**item) for item in items]
    return HistoryResponse(
        code=0,
        data=history_items,
        total=total,
        page=page,
        page_size=page_size,
    )


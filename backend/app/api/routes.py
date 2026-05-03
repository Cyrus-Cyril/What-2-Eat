"""
app/api/routes.py
API 路由 —— 所有前后端交互接口的入口
"""
import logging

from fastapi import APIRouter, Query

from app.models.schemas import (
    RecommendRequest, RecommendResponse,
    FeedbackRequest, FeedbackResponse,
    HistoryResponse, HistoryItem,
    HealthResponse,
)
from app.services.intent_parser import intent_parser
from app.services.recommender import recommend_async
from app.services.user_profile import update_preference_from_feedback
from app.db.crud import save_feedback, get_history

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse, tags=["系统"])
def health_check():
    return HealthResponse(status="ok", version="0.2.0")


@router.post("/recommend", response_model=RecommendResponse, tags=["推荐"])
async def get_recommendation(req: RecommendRequest):
    # 如果有 query，使用 intent_parser 解析并合并参数
    if req.query and req.query.strip():
        req = await intent_parser.parse(
            user_id=req.user_id,
            query=req.query,
            raw_params=req.model_dump()
        )
    return await recommend_async(req)


@router.post("/feedback", response_model=FeedbackResponse, tags=["反馈"])
async def submit_feedback(req: FeedbackRequest):
    logger.info(
        "收到反馈 user=%s restaurant=%s rating=%d chosen=%s",
        req.user_id, req.restaurant_id, req.rating, req.chosen,
    )
    await save_feedback(
        user_id=req.user_id,
        recommendation_id=req.recommendation_id,
        restaurant_id=req.restaurant_id,
        rating=req.rating,
        chosen=req.chosen,
    )
    # 触发偏好更新
    if req.chosen:
        await update_preference_from_feedback(req.user_id, req.restaurant_id, req.rating)
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


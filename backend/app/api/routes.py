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
from app.services.recommender import recommend as run_recommend

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse, tags=["系统"])
def health_check():
    return HealthResponse(status="ok", version="0.1.0")


@router.post("/recommend", response_model=RecommendResponse, tags=["推荐"])
def get_recommendation(req: RecommendRequest):
    return run_recommend(req)


@router.post("/feedback", response_model=FeedbackResponse, tags=["反馈"])
def submit_feedback(req: FeedbackRequest):
    logger.info(
        "收到反馈 user=%s restaurant=%s rating=%d chosen=%s",
        req.user_id, req.restaurant_id, req.rating, req.chosen,
    )
    return FeedbackResponse(code=0, message="反馈已记录（数据库就绪后持久化）")


@router.get("/history", response_model=HistoryResponse, tags=["历史"])
def get_history(
    user_id: str = Query(description="用户标识"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
):
    logger.info("查询历史 user=%s page=%d size=%d", user_id, page, page_size)
    return HistoryResponse(
        code=0,
        data=[],
        total=0,
        page=page,
        page_size=page_size,
    )

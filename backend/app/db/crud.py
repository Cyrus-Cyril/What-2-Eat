"""
app/db/crud.py
数据库增删查改封装
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from sqlalchemy import select, desc

from app.db.database import get_db
from app.db.orm_models import UserQuery, Recommendation, Feedback
from app.models.schemas import RecommendRequest, RestaurantOut

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat()


async def save_query(req: RecommendRequest) -> str:
    """保存一条查询记录，返回 query_id"""
    query_id = str(uuid.uuid4())
    taste_val = req.taste if req.taste else None

    try:
        async with get_db() as db:
            db.add(UserQuery(
                id=query_id,
                user_id=req.user_id,
                longitude=req.longitude,
                latitude=req.latitude,
                radius=req.radius,
                budget_min=req.budget_min,
                budget_max=req.budget_max,
                taste=taste_val,
                query_text=getattr(req, "query", None),
                created_at=_now(),
            ))
    except Exception:
        logger.exception("save_query 失败")
    return query_id


async def save_recommendations(query_id: str, results: list[RestaurantOut]) -> None:
    """批量保存推荐记录"""
    try:
        async with get_db() as db:
            for rank, r in enumerate(results, start=1):
                explain_dict = r.explain.model_dump() if r.explain else {}
                db.add(Recommendation(
                    id=str(uuid.uuid4()),
                    query_id=query_id,
                    restaurant_id=r.restaurant_id,
                    restaurant_name=r.name,
                    rank=rank,
                    final_score=r.score,
                    score_distance=explain_dict.get("scores", {}).get("distance"),
                    score_price=explain_dict.get("scores", {}).get("price"),
                    score_rating=explain_dict.get("scores", {}).get("rating"),
                    score_tag=explain_dict.get("scores", {}).get("tag"),
                    matched_tags=json.dumps(explain_dict.get("matched_tags", []), ensure_ascii=False),
                    reason_hint=json.dumps(explain_dict.get("reason_hint", []), ensure_ascii=False),
                    explain_json=json.dumps(explain_dict, ensure_ascii=False),
                    created_at=_now(),
                ))
    except Exception:
        logger.exception("save_recommendations 失败")


async def save_feedback(
    user_id: str,
    recommendation_id: str | None,
    restaurant_id: str,
    rating: int,
    chosen: bool,
) -> str:
    """保存反馈记录，返回 feedback_id"""
    feedback_id = str(uuid.uuid4())
    try:
        async with get_db() as db:
            db.add(Feedback(
                id=feedback_id,
                user_id=user_id,
                recommendation_id=recommendation_id,
                restaurant_id=restaurant_id,
                rating=rating,
                chosen=1 if chosen else 0,
                created_at=_now(),
            ))
    except Exception:
        logger.exception("save_feedback 失败")
    return feedback_id


async def get_history(user_id: str, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    """
    分页获取用户历史推荐记录。
    返回 (items, total)
    """
    items: list[dict] = []
    total = 0
    try:
        async with get_db() as db:
            # 查出该用户的所有 query_id
            q_ids_rows = await db.execute(
                select(UserQuery.id).where(UserQuery.user_id == user_id)
            )
            q_ids = [r[0] for r in q_ids_rows.all()]
            if not q_ids:
                return [], 0

            # 查推荐记录（排名第1的结果代表每次查询）
            offset = (page - 1) * page_size
            recs_rows = await db.execute(
                select(Recommendation)
                .where(Recommendation.query_id.in_(q_ids), Recommendation.rank == 1)
                .order_by(desc(Recommendation.created_at))
                .offset(offset)
                .limit(page_size)
            )
            recs = recs_rows.scalars().all()

            # 统计总数
            count_rows = await db.execute(
                select(Recommendation.id)
                .where(Recommendation.query_id.in_(q_ids), Recommendation.rank == 1)
            )
            total = len(count_rows.all())

            for r in recs:
                items.append({
                    "query_id": r.query_id or "",
                    "restaurant_name": r.restaurant_name or "",
                    "category": "",
                    "distance_m": 0,
                    "avg_price": 0.0,
                    "score": r.final_score or 0.0,
                    "created_at": r.created_at or "",
                })
    except Exception:
        logger.exception("get_history 失败 user=%s", user_id)
    return items, total

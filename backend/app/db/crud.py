"""
app/db/crud.py
数据库增删查改封装
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, desc

from app.db.database import get_db
from app.db.orm_models import UserQuery, Recommendation, Feedback, Interaction, RestaurantTag, Tag, User, Restaurant
from app.models.schemas import RecommendRequest, RestaurantOut

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now()


async def save_query(req: RecommendRequest) -> str:
    """保存一条查询记录，返回 query_id"""
    query_id = str(uuid.uuid4())
    taste_val = req.taste if req.taste else None

    try:
        async with get_db() as db:
            # ensure user exists to satisfy foreign key constraint
            if req.user_id:
                existing = await db.get(User, req.user_id)
                if existing is None:
                    db.add(User(id=req.user_id))

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
            ))
    except Exception:
        logger.exception("save_query 失败")
    return query_id


async def save_recommendations(query_id: str, results: list[RestaurantOut]) -> None:
    """批量保存推荐记录"""
    try:
        async with get_db() as db:
            # 先 upsert 餐馆数据，满足外键约束
            for r in results:
                await db.merge(Restaurant(
                    id=r.restaurant_id,
                    name=r.name,
                    category=r.category,
                    address=r.address,
                    latitude=r.latitude,
                    longitude=r.longitude,
                    rating=r.rating,
                    avg_price=r.avg_price,
                ))
            # 必须 flush，使餐馆记录先写入 DB，再插入有外键约束的推荐记录
            await db.flush()
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
            ))
    except Exception:
        logger.exception("save_feedback 失败")
    return feedback_id


async def save_interaction(
    user_id: str,
    restaurant_id: str,
    action_type: str,
) -> None:
    """将用户的显式表态（LIKE/DISLIKE）写入 interaction 表。"""
    try:
        async with get_db() as db:
            db.add(Interaction(
                user_id=user_id,
                restaurant_id=restaurant_id,
                action_type=action_type,
            ))
    except Exception:
        logger.exception("save_interaction 失败")


async def get_user_blacklist(user_id: str, hours: int = 24) -> list[str]:
    """
    返回用户近 `hours` 小时内踩过（DISLIKE）的餐厅 ID 列表。
    推荐引擎可据此在候选集中过滤这些餐厅。
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    try:
        async with get_db() as db:
            rows = await db.execute(
                select(Interaction.restaurant_id)
                .where(
                    Interaction.user_id == user_id,
                    Interaction.action_type == "DISLIKE",
                    Interaction.timestamp >= cutoff,
                )
            )
            return [r[0] for r in rows.all()]
    except Exception:
        logger.exception("get_user_blacklist 失败 user=%s", user_id)
        return []


async def get_recent_feedback_context(user_id: str, limit: int = 5) -> dict:
    """
    获取用户最近一批 LIKE/DISLIKE 的标签上下文，供解释系统生成 hello_voice 时使用。

    返回结构：
      {
        "liked_tags":    ["川菜", "火锅"],   # 最近点赞餐厅关联的标签（去重）
        "disliked_tags": ["西餐"],            # 最近踩过餐厅关联的标签（去重）
      }
    """
    context: dict = {"liked_tags": [], "disliked_tags": []}
    try:
        async with get_db() as db:
            # 取最近 N 条 LIKE/DISLIKE 记录
            rows = await db.execute(
                select(Interaction.restaurant_id, Interaction.action_type)
                .where(
                    Interaction.user_id == user_id,
                    Interaction.action_type.in_(["LIKE", "DISLIKE"]),
                )
                .order_by(desc(Interaction.timestamp))
                .limit(limit)
            )
            records = rows.all()
            if not records:
                return context

            liked_rids = {r[0] for r in records if r[1] == "LIKE"}
            disliked_rids = {r[0] for r in records if r[1] == "DISLIKE"}

            async def _get_tags_for_restaurants(rids: set[str]) -> list[str]:
                if not rids:
                    return []
                tag_rows = await db.execute(
                    select(Tag.name)
                    .join(RestaurantTag, RestaurantTag.tag_id == Tag.id)
                    .where(RestaurantTag.restaurant_id.in_(rids))
                )
                return list({r[0] for r in tag_rows.all()})

            context["liked_tags"] = await _get_tags_for_restaurants(liked_rids)
            context["disliked_tags"] = await _get_tags_for_restaurants(disliked_rids)
    except Exception:
        logger.exception("get_recent_feedback_context 失败 user=%s", user_id)
    return context


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

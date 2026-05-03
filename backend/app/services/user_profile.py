"""
app/services/user_profile.py
用户画像服务：读取长期偏好 + feedback 触发偏好更新
"""
from __future__ import annotations
import logging
from datetime import datetime

from sqlalchemy import select, text

from app.db.database import get_db
from app.db.orm_models import UserTagPreference, Tag, Interaction, Feedback, RestaurantTag

logger = logging.getLogger(__name__)

# 学习率
LEARNING_RATE = 0.1


async def get_user_profile(user_id: str) -> dict:
    """
    从数据库聚合用户画像，MVP 阶段若无历史数据则返回空偏好。
    返回字段：
      user_id, avg_budget_max, preferred_tastes, avg_radius, last_location,
      tag_preferences: {tag_name: preference_score}
    """
    profile: dict = {
        "user_id": user_id,
        "avg_budget_max": None,
        "preferred_tastes": [],
        "avg_radius": None,
        "last_location": None,
        "tag_preferences": {},
    }

    try:
        async with get_db() as db:
            # 查询用户标签偏好
            rows = await db.execute(
                select(UserTagPreference, Tag.name)
                .join(Tag, Tag.id == UserTagPreference.tag_id)
                .where(UserTagPreference.user_id == user_id)
                .order_by(UserTagPreference.preference.desc())
            )
            preferences = rows.all()

            if preferences:
                tag_prefs: dict[str, float] = {}
                for pref, tag_name in preferences:
                    tag_prefs[tag_name] = pref.preference
                profile["tag_preferences"] = tag_prefs
                # 偏好 >= 0.6 的 taste 标签作为 preferred_tastes
                profile["preferred_tastes"] = [
                    name for name, score in tag_prefs.items() if score >= 0.6
                ]

            # 查询最近一次查询位置
            last_q = await db.execute(
                text("SELECT longitude, latitude, budget_max, radius FROM user_query "
                     "WHERE user_id = :uid ORDER BY created_at DESC LIMIT 1"),
                {"uid": user_id}
            )
            last = last_q.fetchone()
            if last:
                profile["last_location"] = {"lng": last[0], "lat": last[1]}
                profile["avg_budget_max"] = last[2]
                profile["avg_radius"] = last[3]

    except Exception:
        logger.exception("获取用户画像失败 user_id=%s", user_id)

    return profile


async def update_preference_from_feedback(
    user_id: str,
    restaurant_id: str,
    feedback_rating: int,
) -> None:
    """
    feedback 触发偏好更新：
    History_new(tag) = History_old(tag) + η * feedback_rating * restaurant_tag_weight
    """
    try:
        async with get_db() as db:
            # 获取餐厅关联的所有标签及权重
            rows = await db.execute(
                select(RestaurantTag)
                .where(RestaurantTag.restaurant_id == restaurant_id)
            )
            rt_list = rows.scalars().all()

            now = datetime.now().isoformat()
            for rt in rt_list:
                # 查找或创建用户偏好记录
                pref_row = await db.execute(
                    select(UserTagPreference).where(
                        UserTagPreference.user_id == user_id,
                        UserTagPreference.tag_id == rt.tag_id,
                    )
                )
                pref = pref_row.scalar_one_or_none()

                # 归一化 feedback_rating 到 [0,1]
                normalized_rating = (feedback_rating - 1) / 4.0

                if pref:
                    new_val = pref.preference + LEARNING_RATE * normalized_rating * rt.weight
                    pref.preference = max(0.0, min(1.0, new_val))
                    pref.updated_at = now
                else:
                    new_pref = UserTagPreference(
                        user_id=user_id,
                        tag_id=rt.tag_id,
                        preference=0.5 + LEARNING_RATE * normalized_rating * rt.weight,
                        updated_at=now,
                    )
                    db.add(new_pref)

        logger.info("偏好更新完成 user=%s restaurant=%s rating=%d", user_id, restaurant_id, feedback_rating)
    except Exception:
        logger.exception("偏好更新失败 user=%s", user_id)

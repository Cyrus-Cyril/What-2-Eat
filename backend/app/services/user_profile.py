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

# ── 偏好更新常量 ──────────────────────────────────────────
# 设计文档：Preference(tag) = Preference(tag) + (Action_Weight × Tag_Strength)
LIKE_WEIGHT = 0.1          # 点赞权重
DISLIKE_WEIGHT = -0.2      # 踩权重（负向信号更强烈）
PARENT_DECAY = 0.5         # 父级标签的衰减比例（子标签点赞 → 父标签获得 0.5x 加分）


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
    action_type: str,
) -> None:
    """
    反馈触发偏好更新（显式 LIKE/DISLIKE 驱动）：

    Preference(tag) = Preference(tag) + (Action_Weight × Tag_Strength)
      - LIKE:    Action_Weight = +0.1
      - DISLIKE: Action_Weight = -0.2

    同时对每个标签的父级标签（通过 tag.parent_id）执行层级传递，
    衰减比例 PARENT_DECAY = 0.5（即父级标签得分变化量 = 子级的一半）。

    最终结果 clamp 到 [0.0, 1.0]。
    """
    if action_type not in ("LIKE", "DISLIKE"):
        logger.warning("update_preference_from_feedback: 未知 action_type=%s，跳过", action_type)
        return

    action_weight = LIKE_WEIGHT if action_type == "LIKE" else DISLIKE_WEIGHT

    try:
        async with get_db() as db:
            # 获取餐厅关联的所有标签及权重（Tag_Strength = RestaurantTag.weight）
            rows = await db.execute(
                select(RestaurantTag, Tag.parent_id)
                .join(Tag, Tag.id == RestaurantTag.tag_id)
                .where(RestaurantTag.restaurant_id == restaurant_id)
            )
            rt_pairs = rows.all()   # list of (RestaurantTag, parent_id | None)

            now = datetime.now().isoformat()

            async def _update_tag(tag_id: int, tag_strength: float, weight_multiplier: float) -> None:
                """更新单条 user_tag_preference 记录。"""
                delta = action_weight * tag_strength * weight_multiplier
                pref_row = await db.execute(
                    select(UserTagPreference).where(
                        UserTagPreference.user_id == user_id,
                        UserTagPreference.tag_id == tag_id,
                    )
                )
                pref = pref_row.scalar_one_or_none()
                if pref:
                    pref.preference = max(0.0, min(1.0, pref.preference + delta))
                    pref.updated_at = now
                else:
                    db.add(UserTagPreference(
                        user_id=user_id,
                        tag_id=tag_id,
                        preference=max(0.0, min(1.0, 0.5 + delta)),
                        updated_at=now,
                    ))

            for rt, parent_id in rt_pairs:
                # 1) 更新精确标签
                await _update_tag(rt.tag_id, rt.weight, 1.0)

                # 2) 层级传递：若有父级标签，以 PARENT_DECAY 衰减比例再更新一次
                if parent_id is not None:
                    await _update_tag(parent_id, rt.weight, PARENT_DECAY)

        logger.info(
            "偏好更新完成 user=%s restaurant=%s action=%s",
            user_id, restaurant_id, action_type,
        )
    except Exception:
        logger.exception("偏好更新失败 user=%s", user_id)

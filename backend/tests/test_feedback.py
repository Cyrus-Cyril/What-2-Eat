"""
tests/test_feedback.py
反馈系统单元测试

覆盖：
  1. FeedbackRequest schema 解析（action_type / rating 两种路径）
  2. update_preference_from_feedback：LIKE 提升 / DISLIKE 降低 / 父级层级传递 / clamp
  3. _build_feedback_note：上下文摘要生成
  4. action_type 派生逻辑（路由层规则复现）

运行：
    cd backend && python -m pytest tests/test_feedback.py -v
"""
from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.schemas import FeedbackRequest
from app.services.explanation_builder import _build_feedback_note
from app.services.user_profile import LIKE_WEIGHT, DISLIKE_WEIGHT, PARENT_DECAY


# ── 1. Schema ──────────────────────────────────────────────

class TestFeedbackRequestSchema:
    def test_explicit_like(self):
        req = FeedbackRequest(user_id="u1", restaurant_id="R1", action_type="LIKE", rating=5)
        assert req.action_type == "LIKE"

    def test_explicit_dislike(self):
        req = FeedbackRequest(user_id="u1", restaurant_id="R1", action_type="DISLIKE", rating=1)
        assert req.action_type == "DISLIKE"

    def test_no_action_type_defaults_none(self):
        req = FeedbackRequest(user_id="u1", restaurant_id="R1", rating=3)
        assert req.action_type is None

    def test_invalid_action_type_raises(self):
        with pytest.raises(Exception):
            FeedbackRequest(user_id="u1", restaurant_id="R1", action_type="NEUTRAL", rating=3)

    def test_rating_out_of_range_raises(self):
        with pytest.raises(Exception):
            FeedbackRequest(user_id="u1", restaurant_id="R1", rating=6)

    def test_rating_valid_range(self):
        for r in range(1, 6):
            req = FeedbackRequest(user_id="u1", restaurant_id="R1", rating=r)
            assert req.rating == r


# ── 2. 偏好更新核心逻辑（mock DB） ───────────────────────────

class TestUpdatePreference:

    @pytest.mark.anyio
    async def test_like_increases_preference(self):
        """LIKE 后偏好分应上升"""
        from app.db.orm_models import UserTagPreference
        initial = 0.5
        mock_rt = MagicMock(tag_id=1, weight=1.0)
        mock_pref = MagicMock(spec=UserTagPreference)
        mock_pref.preference = initial

        with patch("app.services.user_profile.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(side_effect=[
                MagicMock(all=MagicMock(return_value=[(mock_rt, None)])),
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_pref)),
            ])
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            from app.services.user_profile import update_preference_from_feedback
            await update_preference_from_feedback("u1", "R1", "LIKE")

        expected = initial + LIKE_WEIGHT * 1.0 * 1.0
        assert abs(mock_pref.preference - expected) < 1e-9

    @pytest.mark.anyio
    async def test_dislike_decreases_preference(self):
        """DISLIKE 后偏好分应下降，且下降幅度比 LIKE 上升幅度大"""
        from app.db.orm_models import UserTagPreference
        initial = 0.6
        mock_rt = MagicMock(tag_id=2, weight=1.0)
        mock_pref = MagicMock(spec=UserTagPreference)
        mock_pref.preference = initial

        with patch("app.services.user_profile.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(side_effect=[
                MagicMock(all=MagicMock(return_value=[(mock_rt, None)])),
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_pref)),
            ])
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            from app.services.user_profile import update_preference_from_feedback
            await update_preference_from_feedback("u1", "R2", "DISLIKE")

        expected = initial + DISLIKE_WEIGHT * 1.0 * 1.0
        assert abs(mock_pref.preference - expected) < 1e-9
        assert mock_pref.preference < initial

    @pytest.mark.anyio
    async def test_parent_tag_updated_with_decay(self):
        """有父级标签时，父级以 PARENT_DECAY 衰减比例一并更新"""
        from app.db.orm_models import UserTagPreference
        initial_child = 0.5
        initial_parent = 0.5
        tag_weight = 0.8
        parent_id = 10

        mock_rt = MagicMock(tag_id=1, weight=tag_weight)
        mock_pref_child = MagicMock(spec=UserTagPreference)
        mock_pref_child.preference = initial_child
        mock_pref_parent = MagicMock(spec=UserTagPreference)
        mock_pref_parent.preference = initial_parent

        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(all=MagicMock(return_value=[(mock_rt, parent_id)]))
            elif call_count == 2:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=mock_pref_child))
            elif call_count == 3:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=mock_pref_parent))
            return MagicMock()

        with patch("app.services.user_profile.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_db.execute = fake_execute
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            from app.services.user_profile import update_preference_from_feedback
            await update_preference_from_feedback("u1", "R1", "LIKE")

        expected_child = initial_child + LIKE_WEIGHT * tag_weight * 1.0
        expected_parent = initial_parent + LIKE_WEIGHT * tag_weight * PARENT_DECAY
        assert abs(mock_pref_child.preference - expected_child) < 1e-9
        assert abs(mock_pref_parent.preference - expected_parent) < 1e-9
        assert mock_pref_parent.preference < mock_pref_child.preference

    @pytest.mark.anyio
    async def test_clamp_upper_bound(self):
        """偏好分不超过 1.0"""
        from app.db.orm_models import UserTagPreference
        mock_rt = MagicMock(tag_id=1, weight=1.0)
        mock_pref = MagicMock(spec=UserTagPreference)
        mock_pref.preference = 0.99

        with patch("app.services.user_profile.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(side_effect=[
                MagicMock(all=MagicMock(return_value=[(mock_rt, None)])),
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_pref)),
            ])
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            from app.services.user_profile import update_preference_from_feedback
            await update_preference_from_feedback("u1", "R1", "LIKE")

        assert mock_pref.preference <= 1.0

    @pytest.mark.anyio
    async def test_clamp_lower_bound(self):
        """偏好分不低于 0.0"""
        from app.db.orm_models import UserTagPreference
        mock_rt = MagicMock(tag_id=1, weight=1.0)
        mock_pref = MagicMock(spec=UserTagPreference)
        mock_pref.preference = 0.01

        with patch("app.services.user_profile.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(side_effect=[
                MagicMock(all=MagicMock(return_value=[(mock_rt, None)])),
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_pref)),
            ])
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            from app.services.user_profile import update_preference_from_feedback
            await update_preference_from_feedback("u1", "R1", "DISLIKE")

        assert mock_pref.preference >= 0.0

    @pytest.mark.anyio
    async def test_unknown_action_type_skips(self):
        """未知 action_type 直接跳过，不操作数据库"""
        with patch("app.services.user_profile.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            from app.services.user_profile import update_preference_from_feedback
            await update_preference_from_feedback("u1", "R1", "NEUTRAL")

        mock_db.execute.assert_not_called()


# ── 3. 反馈上下文摘要 ──────────────────────────────────────

class TestBuildFeedbackNote:
    def test_no_context_returns_empty(self):
        assert _build_feedback_note(None) == ""
        assert _build_feedback_note({}) == ""

    def test_liked_tags_only(self):
        note = _build_feedback_note({"liked_tags": ["川菜", "火锅"], "disliked_tags": []})
        assert "川菜" in note
        assert "赞过" in note
        assert "不太想吃" not in note

    def test_disliked_tags_only(self):
        note = _build_feedback_note({"liked_tags": [], "disliked_tags": ["西餐"]})
        assert "西餐" in note
        assert "不太想吃" in note

    def test_both_tags_present(self):
        note = _build_feedback_note({"liked_tags": ["火锅"], "disliked_tags": ["西餐"]})
        assert "火锅" in note
        assert "西餐" in note

    def test_truncates_to_3_tags(self):
        """最多展示前 3 个标签，第 4 / 5 个不出现"""
        note = _build_feedback_note({
            "liked_tags": ["A", "B", "C", "D", "E"],
            "disliked_tags": [],
        })
        assert "D" not in note
        assert "E" not in note


# ── 4. action_type 派生规则 ────────────────────────────────

class TestActionTypeDeriving:
    """复现路由层的 rating → action_type 转换逻辑并独立验证"""

    @staticmethod
    def derive(action_type, rating) -> str | None:
        at = action_type
        if at is None:
            if rating >= 4:
                at = "LIKE"
            elif rating <= 2:
                at = "DISLIKE"
        return at

    def test_high_rating_becomes_like(self):
        assert self.derive(None, 5) == "LIKE"
        assert self.derive(None, 4) == "LIKE"

    def test_low_rating_becomes_dislike(self):
        assert self.derive(None, 1) == "DISLIKE"
        assert self.derive(None, 2) == "DISLIKE"

    def test_middle_rating_stays_none(self):
        assert self.derive(None, 3) is None

    def test_explicit_dislike_overrides_high_rating(self):
        assert self.derive("DISLIKE", 5) == "DISLIKE"

    def test_explicit_like_overrides_low_rating(self):
        assert self.derive("LIKE", 1) == "LIKE"

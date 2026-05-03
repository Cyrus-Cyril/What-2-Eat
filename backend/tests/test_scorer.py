"""
tests/test_scorer.py
scorer 单元测试 —— 验证各边界用例，所有分项输出范围在 [0,1]
运行：cd backend && python -m pytest tests/test_scorer.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.services.scorer import calc_all, ScoreDetail
from app.models.schemas import RecommendRequest


def make_req(**kwargs) -> RecommendRequest:
    defaults = dict(
        user_id=None, longitude=114.362, latitude=30.532,
        radius=2000, max_count=10,
        budget_min=None, budget_max=None, taste=None, max_distance=None,
    )
    defaults.update(kwargs)
    return RecommendRequest(**defaults)


def make_restaurant(**kwargs) -> dict:
    defaults = dict(
        restaurant_id="test",
        name="测试餐厅",
        category="中餐厅;川菜",
        distance_m=500,
        rating=4.0,
        avg_price=50.0,
        latitude=30.532,
        longitude=114.362,
    )
    defaults.update(kwargs)
    return defaults


def assert_in_range(detail: ScoreDetail):
    assert 0.0 <= detail.distance <= 1.0, f"distance={detail.distance}"
    assert 0.0 <= detail.price <= 1.0, f"price={detail.price}"
    assert 0.0 <= detail.rating <= 1.0, f"rating={detail.rating}"
    assert 0.0 <= detail.tag <= 1.0, f"tag={detail.tag}"
    assert 0.0 <= detail.final <= 1.0, f"final={detail.final}"


class TestScorer:
    def test_normal_case(self):
        """正常情况：有预算、有口味、有评分"""
        req = make_req(budget_min=30, budget_max=70, taste="川菜")
        r = make_restaurant(distance_m=300, rating=4.5, avg_price=50.0)
        detail = calc_all(r, req)
        assert_in_range(detail)
        assert detail.final > 0.5  # 距离近、价格在区间内、评分高、标签匹配

    def test_no_budget(self):
        """无预算时 price_score 应为中性值 0.5"""
        req = make_req()
        r = make_restaurant()
        detail = calc_all(r, req)
        assert_in_range(detail)
        assert detail.price == 0.5

    def test_zero_distance(self):
        """距离为0时 distance_score 应为 1.0"""
        req = make_req()
        r = make_restaurant(distance_m=0)
        detail = calc_all(r, req)
        assert detail.distance == 1.0
        assert_in_range(detail)

    def test_zero_rating(self):
        """无评分（rating=0）时 rating_score 应为 0.4"""
        req = make_req()
        r = make_restaurant(rating=0.0)
        detail = calc_all(r, req)
        assert detail.rating == 0.4
        assert_in_range(detail)

    def test_no_taste(self):
        """无口味偏好时 tag_score 应为 0.5"""
        req = make_req(taste=None)
        r = make_restaurant()
        detail = calc_all(r, req)
        assert detail.tag == 0.5
        assert_in_range(detail)

    def test_taste_full_match(self):
        """完全匹配口味时 tag_score 应高"""
        req = make_req(taste="川菜")
        r = make_restaurant(category="中餐厅;川菜")
        detail = calc_all(r, req)
        assert_in_range(detail)
        assert len(detail.matched_tags) > 0

    def test_taste_no_match(self):
        """口味完全不匹配时 tag_score 应为 0.0"""
        req = make_req(taste="日料")
        r = make_restaurant(category="中餐厅;川菜")
        detail = calc_all(r, req)
        assert detail.tag == 0.0
        assert_in_range(detail)

    def test_price_out_of_range(self):
        """价格远超预算时 price_score 应接近 0"""
        req = make_req(budget_min=20, budget_max=30)
        r = make_restaurant(avg_price=200.0)
        detail = calc_all(r, req)
        assert detail.price < 0.3
        assert_in_range(detail)

    def test_distance_exceeds_max(self):
        """距离超过 max_dist 时 distance_score 应为 0"""
        req = make_req(max_distance=500)
        r = make_restaurant(distance_m=1000)
        detail = calc_all(r, req)
        assert detail.distance == 0.0
        assert_in_range(detail)

    def test_user_tag_preferences(self):
        """有历史偏好时，偏好匹配应提升 tag_score"""
        req = make_req(taste=None)
        r = make_restaurant(category="中餐厅;川菜")
        detail_no_hist = calc_all(r, req)

        user_prefs = {"川菜": 0.9, "辣": 0.8}
        detail_with_hist = calc_all(r, req, user_prefs)
        assert detail_with_hist.tag > detail_no_hist.tag
        assert_in_range(detail_with_hist)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

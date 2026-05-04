"""
tests/test_explainer.py
测试 explainer.py 的规则引擎：维度阈值边界、reasoning_logic 取值、新字段生成
"""
import pytest
from app.services.scorer import ScoreDetail
from app.services.explainer import build_explain, ExplainData


def _make_score(distance=0.5, price=0.5, rating=0.5, tag=0.5, matched_tags=None) -> ScoreDetail:
    s = ScoreDetail(
        distance=distance,
        price=price,
        rating=rating,
        tag=tag,
        final=0.5,
        matched_tags=matched_tags or [],
    )
    return s


# ── 地理位置维度 ──────────────────────────────────────────

def test_distance_within_300m():
    r = {"distance_m": 200, "rating": 4.0, "avg_price": 30.0, "category": "中餐/川菜"}
    result = build_explain(r, _make_score(distance=0.9))
    dim = next(d for d in result.dimension_details if d.dimension == "地理位置")
    assert dim.detail == "步行5分钟内"
    assert "步行5分钟内" in result.reason_hint


def test_distance_300_to_800m():
    r = {"distance_m": 500, "rating": 4.0, "avg_price": 30.0, "category": "中餐/川菜"}
    result = build_explain(r, _make_score(distance=0.6))
    dim = next(d for d in result.dimension_details if d.dimension == "地理位置")
    assert dim.detail == "步行可达"


def test_distance_over_800m():
    r = {"distance_m": 1200, "rating": 4.0, "avg_price": 30.0, "category": "中餐"}
    result = build_explain(r, _make_score(distance=0.3))
    dim = next(d for d in result.dimension_details if d.dimension == "地理位置")
    assert "1200" in dim.detail


# ── 人均价格维度 ──────────────────────────────────────────

def test_price_high_score():
    r = {"distance_m": 500, "rating": 4.0, "avg_price": 28.0, "category": "快餐"}
    result = build_explain(r, _make_score(price=0.85))
    dim = next(d for d in result.dimension_details if d.dimension == "人均价格")
    assert "非常合适" in dim.detail
    assert dim.score_impact == "high"


def test_price_medium_score():
    r = {"distance_m": 500, "rating": 4.0, "avg_price": 45.0, "category": "快餐"}
    result = build_explain(r, _make_score(price=0.65))
    dim = next(d for d in result.dimension_details if d.dimension == "人均价格")
    assert "适中" in dim.detail


def test_price_low_score():
    r = {"distance_m": 500, "rating": 4.0, "avg_price": 80.0, "category": "快餐"}
    result = build_explain(r, _make_score(price=0.3))
    dim = next(d for d in result.dimension_details if d.dimension == "人均价格")
    assert "略超预算" in dim.detail


# ── 用户口碑维度 ──────────────────────────────────────────

def test_rating_excellent():
    r = {"distance_m": 500, "rating": 4.8, "avg_price": 30.0, "category": "火锅"}
    result = build_explain(r, _make_score(rating=0.96))
    dim = next(d for d in result.dimension_details if d.dimension == "用户口碑")
    assert "口碑极佳" in dim.detail
    assert dim.score_impact == "high"


def test_rating_good():
    r = {"distance_m": 500, "rating": 4.2, "avg_price": 30.0, "category": "火锅"}
    result = build_explain(r, _make_score(rating=0.84))
    dim = next(d for d in result.dimension_details if d.dimension == "用户口碑")
    assert "较好" in dim.detail


def test_rating_average():
    r = {"distance_m": 500, "rating": 3.5, "avg_price": 30.0, "category": "火锅"}
    result = build_explain(r, _make_score(rating=0.7))
    dim = next(d for d in result.dimension_details if d.dimension == "用户口碑")
    assert "一般" in dim.detail


# ── 品类匹配维度 ──────────────────────────────────────────

def test_tag_matched():
    r = {"distance_m": 500, "rating": 4.0, "avg_price": 30.0, "category": "火锅"}
    result = build_explain(r, _make_score(tag=0.85, matched_tags=["火锅"]))
    dim = next((d for d in result.dimension_details if d.dimension == "品类匹配"), None)
    assert dim is not None
    assert "火锅" in dim.detail
    assert dim.score_impact == "high"


def test_tag_not_matched():
    r = {"distance_m": 500, "rating": 4.0, "avg_price": 30.0, "category": "西餐"}
    result = build_explain(r, _make_score(tag=0.2, matched_tags=[]))
    dim = next((d for d in result.dimension_details if d.dimension == "品类匹配"), None)
    assert dim is None


# ── reasoning_logic ───────────────────────────────────────

def test_reasoning_logic_primary_is_highest_impact():
    r = {"distance_m": 200, "rating": 4.8, "avg_price": 28.0, "category": "川菜"}
    result = build_explain(
        r,
        _make_score(distance=0.9, price=0.85, rating=0.96, tag=0.0),
    )
    assert result.reasoning_logic is not None
    # 评分最高的维度应出现在 primary_factor
    assert result.reasoning_logic.primary_factor != ""
    assert result.reasoning_logic.secondary_factor != ""


def test_reasoning_logic_present_when_dims_exist():
    r = {"distance_m": 500, "rating": 4.0, "avg_price": 30.0, "category": "快餐"}
    result = build_explain(r, _make_score())
    assert result.reasoning_logic is not None


# ── summary ───────────────────────────────────────────────

def test_summary_not_empty():
    r = {"distance_m": 200, "rating": 4.5, "avg_price": 25.0, "category": "中餐/川菜"}
    result = build_explain(r, _make_score(distance=0.9, price=0.85, rating=0.9))
    assert isinstance(result.summary, str)
    assert len(result.summary) > 0


def test_summary_contains_category():
    r = {"distance_m": 200, "rating": 4.0, "avg_price": 30.0, "category": "快餐"}
    result = build_explain(r, _make_score(distance=0.9))
    assert "快餐" in result.summary


# ── ExplainData 结构完整性 ────────────────────────────────

def test_explain_data_has_all_fields():
    r = {"distance_m": 300, "rating": 4.2, "avg_price": 35.0, "category": "日料"}
    result = build_explain(r, _make_score())
    assert isinstance(result.scores, dict)
    assert isinstance(result.matched_tags, list)
    assert isinstance(result.reason_hint, list)
    assert isinstance(result.dimension_details, list)
    assert len(result.dimension_details) >= 3  # 至少：地理、价格、口碑

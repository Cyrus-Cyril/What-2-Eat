"""
app/services/preset_recommender.py
预设偏好推荐引擎 —— 不调用 LLM，基于用户预设偏好标签直接打分

与主推荐引擎 recommender.py 的区别：
  - 不经过 intent_parser（不调用 LLM）
  - 不使用 PenaltyCalculator（无 S 曲线/指数衰减）
  - 不走三层弹性约束架构
  - 直接从高德 API 获取真实餐厅数据

核心设计原则：
  - 距离 = 二值门控：在 distance_preference 以内保留，超出排除
  - 标签 = 分层排序：有标签匹配的餐厅强制排在无匹配的前面
    同一层级内按 Tag + Budget + Rating 评分排序
  - 不剔除任何在距离范围内的餐厅，但标签匹配的始终优先

评分公式：
  TagScore   = matched_count / len(user_tags)      [0~1]  (零匹配→0)
  BudgetFit  = 1.0 if in range, else linear decay   [0~1]
  RatingNrm  = rating / 5.0                          [0~1]

  FinalScore = 0.50*Tag + 0.30*Budget + 0.20*Rating + TasteBonus + FavBonus

排序键：(-has_match, -score)，确保有匹配的永远排在无匹配的前面

返回：分层排序后的 Top-N 餐馆卡片
"""
from __future__ import annotations

import logging

from app.models.schemas import PresetRecommendRequest, PresetRestaurantCard
from app.services.tag_mapper import get_tags, get_amap_types_for_tags, get_keywords_for_tags
from app.services.data_entry import get_candidate_restaurants

logger = logging.getLogger(__name__)

_W_TAG = 0.50
_W_BUDGET = 0.30
_W_RATING = 0.20


def _tag_check(restaurant: dict, user_tags: list[str]) -> tuple[bool, list[str]]:
    """
    标签匹配检查（不过滤，仅计算匹配）。
    优先使用 amap_type_path（完整路径），fallback 到 category（最后一段）。
    补充策略：如果name中包含关键词，额外添加对应标签。
    返回 (has_match, shared_tags)。
    """
    if not user_tags:
        return False, []

    type_path = restaurant.get("amap_type_path", "") or ""
    category = restaurant.get("category", "") or ""
    source = type_path if type_path else category
    r_tags = get_tags(source)

    # 智能补充：根据餐厅名称添加缺失的标签（全面覆盖）
    name = restaurant.get("name", "") or ""
    name_lower = name.lower()

    # ── 烧烤类 ──
    if any(kw in name for kw in ["烧烤", "烤肉", "炭烤", "铁板烧"]):
        if "烧烤" not in r_tags:
            r_tags.append("烧烤")

    # ── 火锅类 ──
    if any(kw in name for kw in ["火锅", "串串", "麻辣烫", "冒菜", "焖锅"]):
        if "火锅" not in r_tags:
            r_tags.append("火锅")

    # ── 西餐类 ──
    if any(kw in name for kw in ["西餐", "牛排", "披萨", "比萨", "意大利", "沙拉"]):
        if "西餐" not in r_tags:
            r_tags.append("西餐")

    # ── 日料类 ──
    if any(kw in name for kw in ["日本", "日式", "寿司", "刺身", "料理", "拉面", "寿喜烧", "日料"]):
        if "日料" not in r_tags:
            r_tags.append("日料")

    # ── 韩餐类 ──
    if any(kw in name for kw in ["韩国", "韩式", "韩国料理", "烤肉", "泡菜", "石锅拌饭", "韩餐"]):
        if "韩餐" not in r_tags:
            r_tags.append("韩餐")

    # ── 快餐类 ──
    if any(kw in name for kw in ["快餐", "汉堡", "炸鸡", "肯德基", "麦当劳", "华莱士", "必胜客", "比格"]):
        if "快餐" not in r_tags:
            r_tags.append("快餐")

    # ── 咖啡/饮品类 ──
    if any(kw in name for kw in ["咖啡", "星巴克", "瑞幸", "漫咖啡", "咖啡厅"]):
        if "咖啡" not in r_tags:
            r_tags.append("咖啡")
        if "饮品" not in r_tags:
            r_tags.append("饮品")

    if any(kw in name for kw in ["奶茶", "喜茶", "奈雪", "茶颜", "霸王茶姬", "古茗", "蜜雪冰城", "柠季"]):
        if "饮品" not in r_tags:
            r_tags.append("饮品")
        if "奶茶" not in r_tags:
            r_tags.append("奶茶")
        if "甜" not in r_tags:
            r_tags.append("甜")

    if any(kw in name for kw in ["冷饮", "柠檬茶", "果茶", "冰粉", "冰可乐"]):
        if "饮品" not in r_tags:
            r_tags.append("饮品")

    # ── 甜品/面包类 ──
    if any(kw in name for kw in ["甜品", "蛋糕", "烘焙", "面包房", "甜点", "冰淇淋", "DQ", "秋日"]):
        if "甜品" not in r_tags:
            r_tags.append("甜品")
        if "甜" not in r_tags:
            r_tags.append("甜")
        if "面包" not in r_tags and ("面包" in name or "烘焙" in name):
            r_tags.append("面包")

    # ── 面食类 ──
    if any(kw in name for kw in ["面", "面条", "拉面", "米粉", "米线", "饺子", "馄饨", "兰州", "热干面"]):
        if "面食" not in r_tags:
            r_tags.append("面食")

    # ── 东南亚类 ──
    if any(kw in name for kw in ["泰国", "越南", "印度", "咖喱", "冬阴功", "东南亚"]):
        if "东南亚" not in r_tags:
            r_tags.append("东南亚")

    # ── 海鲜类 ──
    if any(kw in name for kw in ["海鲜", "龙虾", "螃蟹", "贝类", "鱼鲜", "水产"]):
        if "海鲜" not in r_tags:
            r_tags.append("海鲜")

    # ── 小吃类（兜底）──
    if any(kw in name for kw in ["小吃", "早餐", "包子", "煎饼", "鸭脖", "卤味"]):
        if "小吃" not in r_tags:
            r_tags.append("小吃")

    shared = [t for t in user_tags if t in r_tags]
    return len(shared) > 0, shared


def _score_preset(
    restaurant: dict, req: PresetRecommendRequest, shared_tags: list[str],
) -> tuple[float, list[str], str]:
    """
    对餐厅评分。返回 (score, shared_tags, reason)。
    零匹配餐厅仍会打分，但 tag_score=0 导致基础分偏低，且最终会被排在匹配餐厅之后。
    """
    name = restaurant.get("name", "?")
    type_path = restaurant.get("amap_type_path", "") or ""
    category = restaurant.get("category", "") or ""
    source_for_tags = type_path if type_path else category
    price = float(restaurant.get("avg_price", 0) or 0)
    rating = float(restaurant.get("rating", 0) or 0)
    user_tags = req.preference_tags

    r_tags = get_tags(source_for_tags)

    # 智能补充：根据餐厅名称添加缺失的标签（与_tag_check保持完全一致）
    if any(kw in name for kw in ["烧烤", "烤肉", "炭烤", "铁板烧"]):
        if "烧烤" not in r_tags:
            r_tags.append("烧烤")
    if any(kw in name for kw in ["火锅", "串串", "麻辣烫", "冒菜", "焖锅"]):
        if "火锅" not in r_tags:
            r_tags.append("火锅")
    if any(kw in name for kw in ["西餐", "牛排", "披萨", "比萨", "意大利", "沙拉"]):
        if "西餐" not in r_tags:
            r_tags.append("西餐")
    if any(kw in name for kw in ["日本", "日式", "寿司", "刺身", "料理", "拉面", "寿喜烧", "日料"]):
        if "日料" not in r_tags:
            r_tags.append("日料")
    if any(kw in name for kw in ["韩国", "韩式", "韩国料理", "烤肉", "泡菜", "石锅拌饭", "韩餐"]):
        if "韩餐" not in r_tags:
            r_tags.append("韩餐")
    if any(kw in name for kw in ["快餐", "汉堡", "炸鸡", "肯德基", "麦当劳", "华莱士", "必胜客", "比格"]):
        if "快餐" not in r_tags:
            r_tags.append("快餐")
    if any(kw in name for kw in ["咖啡", "星巴克", "瑞幸", "漫咖啡", "咖啡厅"]):
        if "咖啡" not in r_tags:
            r_tags.append("咖啡")
        if "饮品" not in r_tags:
            r_tags.append("饮品")
    if any(kw in name for kw in ["奶茶", "喜茶", "奈雪", "茶颜", "霸王茶姬", "古茗", "蜜雪冰城", "柠季"]):
        if "饮品" not in r_tags:
            r_tags.append("饮品")
        if "奶茶" not in r_tags:
            r_tags.append("奶茶")
    if any(kw in name for kw in ["甜品", "蛋糕", "烘焙", "面包房", "甜点", "冰淇淋", "DQ", "秋日"]):
        if "甜品" not in r_tags:
            r_tags.append("甜品")
    if ("面包" in name or "烘焙" in name) and "面包" not in r_tags:
        r_tags.append("面包")
    if any(kw in name for kw in ["面", "面条", "拉面", "米粉", "米线", "饺子", "馄饨", "兰州", "热干面"]):
        if "面食" not in r_tags:
            r_tags.append("面食")
    if any(kw in name for kw in ["泰国", "越南", "印度", "咖喱", "冬阴功", "东南亚"]):
        if "东南亚" not in r_tags:
            r_tags.append("东南亚")
    if any(kw in name for kw in ["海鲜", "龙虾", "螃蟹", "贝类", "鱼鲜", "水产"]):
        if "海鲜" not in r_tags:
            r_tags.append("海鲜")

    # ── 1. 标签匹配分 ────────────────────────────────────────
    # 多标签策略：满足任意一个标签即给高分（0.9+），匹配多个标签额外加分
    if not user_tags:
        tag_score = 0.5
    elif len(shared_tags) == 0:
        tag_score = 0.0
    elif len(shared_tags) >= len(user_tags):
        tag_score = 1.0  # 匹配所有标签，满分
    else:
        # 匹配部分标签：基础分0.9 + 每个匹配标签的加成（最多到1.0）
        base_score = 0.9
        bonus_per_tag = min(0.1 / max(len(user_tags) - 1, 1), 0.05)
        tag_score = min(1.0, base_score + len(shared_tags) * bonus_per_tag)

    logger.debug(
        "[preset] 标签分 %s user_tags=%s r_tags=%s shared=%s → %.4f",
        name, user_tags, r_tags, shared_tags, tag_score,
    )

    # ── 2. 预算匹配分 ────────────────────────────────────────
    b_min = req.budget_min or 0
    b_max = req.budget_max or 100
    if price <= 0:
        budget_score = 0.5
        logger.debug("[preset] 预算分 %s price=0 → 中性分 0.5", name)
    elif b_min <= price <= b_max:
        budget_score = 1.0
        logger.debug("[preset] 预算分 %s price=%.1f in [%.0f,%.0f] → 1.0", name, price, b_min, b_max)
    else:
        mid = (b_min + b_max) / 2
        tol = max(20, (b_max - b_min) / 2 + 10)
        budget_score = max(0.0, 1.0 - abs(price - mid) / tol)
        logger.debug(
            "[preset] 预算分 %s price=%.1f not in [%.0f,%.0f] mid=%.1f tol=%.1f → %.4f",
            name, price, b_min, b_max, mid, tol, budget_score,
        )

    # ── 3. 评分归一化 ────────────────────────────────────────
    rating_score = rating / 5.0 if rating > 0 else 0.4
    logger.debug("[preset] 评分分 %s rating=%.1f → %.4f", name, rating, rating_score)

    # ── 4. 口味倾向加成 ──────────────────────────────────────
    taste_bonus = 0.0
    spicy_tags = {"川菜", "火锅", "麻辣", "辣"}
    healthy_tags = {"轻食", "健康饮食", "沙拉", "素食", "低脂"}
    sweet_tags = {"甜品", "甜", "面包", "奶茶"}

    if req.spicy_preference > 0.7 and any(t in r_tags for t in spicy_tags):
        bonus = (req.spicy_preference - 0.5) * 0.20
        taste_bonus += bonus
        logger.debug("[preset] 辣度加成 %s spicy=%.2f → +%.4f", name, req.spicy_preference, bonus)

    if req.healthy_preference > 0.7 and any(t in r_tags for t in healthy_tags):
        bonus = (req.healthy_preference - 0.5) * 0.20
        taste_bonus += bonus
        logger.debug("[preset] 健康加成 %s healthy=%.2f → +%.4f", name, req.healthy_preference, bonus)

    if req.sweet_preference > 0.7 and any(t in r_tags for t in sweet_tags):
        bonus = (req.sweet_preference - 0.5) * 0.20
        taste_bonus += bonus
        logger.debug("[preset] 甜度加成 %s sweet=%.2f → +%.4f", name, req.sweet_preference, bonus)

    # ── 5. 收藏加成 ──────────────────────────────────────────
    fav_bonus = 0.0
    if req.favorites and name in req.favorites:
        fav_bonus = 0.16
        logger.debug("[preset] 收藏加成 %s → +0.16", name)

    # ── 6. 综合得分 ──────────────────────────────────────────
    base = (
        _W_TAG * tag_score
        + _W_BUDGET * budget_score
        + _W_RATING * rating_score
    )
    final = min(1.0, base + taste_bonus + fav_bonus)
    logger.debug(
        "[preset] 最终得分 %s base=%.4f taste=%.4f fav=%.4f → %.4f",
        name, base, taste_bonus, fav_bonus, final,
    )

    # ── 7. 生成推荐理由 ──────────────────────────────────────
    reason_parts: list[str] = []
    if shared_tags:
        reason_parts.append(f"口味偏好匹配了{','.join(shared_tags[:2])}")
    if b_min <= price <= b_max:
        reason_parts.append("在你的预算范围内")
    if rating_score > 0.8:
        reason_parts.append("评分很高")
    if fav_bonus > 0:
        reason_parts.append("这是你的收藏店铺")

    reason = "，".join(reason_parts[:2]) if reason_parts else "综合条件较匹配"

    return final, shared_tags, reason


def _build_cards(
    scored: list[tuple[bool, float, dict, list[str], str]],
    top_n: int,
) -> list[PresetRestaurantCard]:
    """将评分结果构建为前端卡片列表。"""
    result: list[PresetRestaurantCard] = []
    for _, score, r, shared_tags, reason in scored[:top_n]:
        r_tags = get_tags(r.get("category", "") or "")
        result.append(PresetRestaurantCard(
            id=r.get("restaurant_id", ""),
            name=r.get("name", ""),
            category=r.get("category", ""),
            tags=r_tags,
            avg_price=float(r.get("avg_price", 0.0) or 0.0),
            rating=float(r.get("rating", 0.0) or 0.0),
            distance_m=int(r.get("distance_m", 0) or 0),
            address=r.get("address", ""),
            reason=reason,
            shared_tags=shared_tags,
            score=round(score, 4),
        ))
    return result


async def _fetch_and_score(
    req: PresetRecommendRequest,
    search_radius: int,
) -> list[tuple[bool, float, dict, list[str], str]]:
    """
    单轮获取+过滤+打分流程：
      1. 用 api_radius（≥ 3× search_radius 或 3000m）从高德拉取 3 页（最多 75 条）
      2. 硬过滤：距离超出 distance_preference 的直接排除
      3. 所有距离内餐厅逐家打分（标签不匹配的也保留，但 tag_score=0）
      4. 分层排序：有标签匹配的优先，同层级按分数降序

    返回 (has_match, score, restaurant_dict, shared_tags, reason) 列表。
    """
    max_dist = req.distance_preference or 2000
    api_radius = max(search_radius * 3, 3000)
    # 优化：减少API调用次数（2页×25条=50条足够推荐6-10条）
    # 有关键词搜索时更精确，2页足够；无关键词时也减少到2页提升速度
    page_count = 2

    # 根据用户标签动态构建高德API的types和keywords参数
    dynamic_types = get_amap_types_for_tags(req.preference_tags)
    dynamic_keywords = get_keywords_for_tags(req.preference_tags)
    logger.info("预设推荐动态参数: tags=%s → types=%s keywords=%s", req.preference_tags, dynamic_types, dynamic_keywords)

    candidates = await get_candidate_restaurants(
        longitude=req.longitude,
        latitude=req.latitude,
        radius=api_radius,
        max_count=25,
        max_pages=page_count,
        types=dynamic_types,  # 传入动态types
        keywords=dynamic_keywords,  # 传入动态keywords（精确搜索）
    )

    if not candidates:
        logger.warning("预设推荐：周边 api_radius=%d 无候选餐厅", api_radius)
        return []

    scored: list[tuple[bool, float, dict, list[str], str]] = []
    seen_ids: set[str] = set()
    dist_dropped = 0
    with_match = 0
    without_match = 0
    dup_dropped = 0

    for r in candidates:
        rid = r.get("restaurant_id", "")
        if rid in seen_ids:
            dup_dropped += 1
            continue
        seen_ids.add(rid)

        distance = int(r.get("distance_m", 0) or 0)
        if distance > max_dist:
            dist_dropped += 1
            continue

        has_match, shared_tags = _tag_check(r, req.preference_tags)
        score, shared_tags, reason = _score_preset(r, req, shared_tags)
        scored.append((has_match, score, r, shared_tags, reason))

        if has_match:
            with_match += 1
        else:
            without_match += 1

    logger.info(
        "预设评分 api_radius=%d max_dist=%d: 总数=%d, 去重=%d, 距离排除=%d, 有标签匹配=%d, 无匹配=%d",
        api_radius, max_dist, len(candidates), dup_dropped, dist_dropped, with_match, without_match,
    )

    # 分层排序：has_match=True 的优先，同层按 score 降序
    scored.sort(key=lambda x: (not x[0], -x[1]))
    return scored


async def recommend_by_preset(req: PresetRecommendRequest) -> list[PresetRestaurantCard]:
    """
    预设偏好推荐主流程：
      1. 以 distance_preference 为搜索半径，拉取+打分+分层排序
      2. 无结果时搜索半径扩展至 2× 兜底
      3. 返回 Top-N
    """
    base_radius = req.distance_preference or 2000

    logger.info(
        "预设推荐请求 user=%s (%.4f,%.4f) dist=%d budget=[%.0f,%.0f] tags=%s max=%d",
        req.user_id, req.longitude, req.latitude,
        req.distance_preference, req.budget_min, req.budget_max,
        req.preference_tags, req.max_count,
    )

    try:
        scored = await _fetch_and_score(req, base_radius)
    except Exception:
        logger.exception("预设推荐获取数据失败")
        return []

    if not scored and base_radius < 5000:
        expanded = min(base_radius * 2, 5000)
        logger.info("硬过滤无结果，扩展搜索半径 %d → %d 兜底", base_radius, expanded)
        try:
            scored = await _fetch_and_score(req, expanded)
        except Exception:
            logger.exception("预设推荐兜底获取数据失败")
            return []

    if not scored:
        logger.warning("预设推荐：无候选餐厅")
        return []

    matched_count = sum(1 for has_match, *_ in scored if has_match)
    if req.preference_tags and matched_count >= req.max_count:
        scored = [item for item in scored if item[0]]
        logger.info("标签匹配充足 (%d ≥ %d)，剔除全部无匹配餐厅", matched_count, req.max_count)

    return _build_cards(scored, req.max_count)

"""
app/services/tag_mapper.py
category（高德原始分类字符串）→ tag_name 列表的映射

映射策略：
1. 关键词匹配：遍历 CATEGORY_TAG_MAP，若 category 包含 key，则添加对应 tags
2. 返回去重后的 tag_name 列表
"""
from __future__ import annotations

# key: 高德 category 关键词（小写匹配）
# value: 对应的标签名列表（与 seed.sql 中 tag.name 一致）
CATEGORY_TAG_MAP: dict[str, list[str]] = {
    "川菜":   ["川菜", "中餐", "辣"],
    "火锅":   ["火锅", "中餐", "辣"],
    "粤菜":   ["粤菜", "中餐", "清淡", "咸鲜"],
    "湘菜":   ["湘菜", "中餐", "辣"],
    "烧烤":   ["烧烤", "中餐"],
    "面食":   ["面食", "中餐"],
    "米粉":   ["米粉", "中餐", "清淡"],
    "面条":   ["面食", "中餐"],
    "小吃":   ["中餐"],
    "中餐":   ["中餐"],
    "日本料理": ["日料", "咸鲜"],
    "拉面":   ["日料", "面食"],
    "寿司":   ["日料", "咸鲜"],
    "韩国料理": ["韩餐"],
    "烤肉":   ["韩餐", "烧烤"],
    "西餐":   ["西餐"],
    "牛排":   ["西餐"],
    "意大利": ["西餐"],
    "快餐":   ["快餐"],
    "炸鸡":   ["快餐", "辣"],
    "汉堡":   ["快餐"],
    "素食":   ["中餐", "清淡"],
    "海鲜":   ["中餐", "咸鲜"],
    "东南亚": ["清淡", "辣"],
    "泰国":   ["清淡", "辣"],
}


def get_tags(category: str) -> list[str]:
    """
    根据高德 category 字段（如 "中餐厅;川菜"）返回匹配的标签名列表。
    """
    if not category:
        return []
    result: set[str] = set()
    cat_lower = category.lower()
    for keyword, tags in CATEGORY_TAG_MAP.items():
        if keyword.lower() in cat_lower:
            result.update(tags)
    return list(result)


# 标签向上级语义泛化映射：精确标签 → 父级标签列表
# 用于 Scene C 迭代松弛搜索第三步（语义泛化）
_TAG_PARENT_MAP: dict[str, list[str]] = {
    "火锅":  ["川菜", "中餐", "辣"],
    "川菜":  ["中餐", "辣"],
    "湘菜":  ["中餐", "辣"],
    "烧烤":  ["中餐"],
    "面食":  ["中餐"],
    "日料":  ["咸鲜"],
    "韩餐":  ["中餐", "烧烤"],
    "快餐":  ["中餐"],
    "粤菜":  ["中餐", "清淡"],
    "米粉":  ["中餐", "清淡"],
    "海鲜":  ["中餐", "咸鲜"],
    "西餐":  ["咸鲜"],
}


def get_parent_tags(tags: list[str]) -> list[str]:
    """
    将精确标签列表扩展为上级语义标签（用于迭代松弛搜索第三步）。
    例如：["火锅"] -> ["川菜", "中餐", "辣"]
    """
    result: set[str] = set()
    for t in tags:
        result.update(_TAG_PARENT_MAP.get(t, []))
    return list(result)


# tag.name → tag.type 映射（与 mysql_schema.sql 中 type 枚举一致）
_TAG_TYPE_MAP: dict[str, str] = {
    # cuisine
    "中餐":  "cuisine",
    "川菜":  "cuisine",
    "粤菜":  "cuisine",
    "湘菜":  "cuisine",
    "日料":  "cuisine",
    "韩餐":  "cuisine",
    "西餐":  "cuisine",
    # taste
    "辣":   "taste",
    "清淡":  "taste",
    "咸鲜":  "taste",
    # type
    "快餐":  "type",
    "火锅":  "type",
    "烧烤":  "type",
    "面食":  "type",
    "米粉":  "type",
    "海鲜":  "type",
}


def get_tag_type(tag_name: str) -> str:
    """返回标签对应的 type 字段值，未知标签默认 'cuisine'。"""
    return _TAG_TYPE_MAP.get(tag_name, "cuisine")

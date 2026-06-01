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
    # ── 中式正餐 ──
    "川菜":   ["川菜", "中餐", "辣"],
    "冒菜":   ["川菜", "中餐", "辣"],
    "酸菜鱼": ["川菜", "中餐", "辣"],
    "火锅":   ["火锅", "中餐", "辣"],
    "串串":   ["火锅", "中餐", "辣"],
    "麻辣烫": ["火锅", "中餐", "辣"],
    "焖锅":   ["火锅", "中餐"],
    "粤菜":   ["粤菜", "中餐", "清淡"],
    "茶餐厅": ["粤菜", "中餐", "清淡"],
    "湘菜":   ["湘菜", "中餐", "辣"],
    "小龙虾": ["湘菜", "中餐", "辣"],
    "烧烤":   ["烧烤", "中餐"],
    "海鲜":   ["海鲜", "中餐", "咸鲜"],
    "素食":   ["素食", "中餐", "清淡"],
    "中餐":   ["中餐"],
    "中餐厅": ["中餐"],  # 高德中间层级
    "特色/地方风味餐厅": ["中餐"],  # 高德泛分类
    # ── 面点小吃 ──
    "面食":   ["面食", "中餐"],
    "面条":   ["面食", "中餐"],
    "饺子":   ["面食", "中餐"],
    "馄饨":   ["面食", "中餐"],
    "包子":   ["面食", "中餐"],
    "米粉":   ["米粉", "中餐", "清淡"],
    "小吃":   ["小吃", "中餐"],
    "麻辣":   ["小吃", "中餐", "辣"],
    # ── 日料 ──
    "日本料理": ["日料", "咸鲜"],
    "日式":   ["日料", "咸鲜"],
    "拉面":   ["日料", "面食"],
    "寿司":   ["日料", "咸鲜"],
    # ── 韩餐 ──
    "韩国料理": ["韩餐"],
    "韩国":   ["韩餐"],
    "韩式":   ["韩餐"],
    "烤肉":   ["韩餐", "烧烤"],
    # ── 西餐 ──
    "西餐":   ["西餐"],
    "牛排":   ["西餐"],
    "意大利": ["西餐"],
    "披萨":   ["西餐"],
     "比萨":   ["西餐"],
    # ── 快餐 ──
    "快餐":   ["快餐"],
    "汉堡":   ["快餐", "西餐"],
    "三明治": ["快餐", "西餐"],
    "炸鸡":   ["快餐", "辣"],
    "炸串":   ["快餐", "辣"],
    # ── 东南亚 ──
    "东南亚": ["东南亚", "清淡", "辣"],
    "泰国":   ["东南亚", "清淡", "辣"],
    "越南":   ["东南亚", "清淡"],
    "印度":   ["东南亚", "辣"],
    # ── 饮品甜品 ──
    "咖啡":   ["饮品", "咖啡"],
    "奶茶":   ["饮品", "甜"],
    "冷饮":   ["饮品"],
    "茶饮":   ["饮品"],
    "甜品":   ["甜品", "甜"],
    "冰淇淋": ["甜品", "甜"],
    "面包":   ["面包", "甜"],
    "糕点":   ["面包", "甜"],
    "蛋糕":   ["甜品", "甜"],
    # ── 高德特殊分类 ──
    "鸡":     ["快餐", "中餐"],  # 老乡鸡等
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


def extract_restaurant_tags(restaurant: dict) -> list[str]:
    """
    从餐厅数据中提取标签（供所有推荐引擎共用）。

    策略：
    1. 优先用 amap_type_path（完整路径），fallback 到 category
    2. 调用 get_tags() 做关键词匹配
    3. 根据餐厅名称做智能补充（name fallback）
    返回去重后的标签列表。
    """
    type_path = restaurant.get("amap_type_path", "") or ""
    category = restaurant.get("category", "") or ""
    source = type_path if type_path else category
    r_tags = get_tags(source)

    name = restaurant.get("name", "") or ""

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
    if any(kw in name for kw in ["韩国", "韩式", "韩国料理", "泡菜", "石锅拌饭", "韩餐"]):
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

    return r_tags


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


# ── 标签 → 高德POI typecode 映射（用于动态API调用）──
# 根据用户偏好标签，构建高德API的types参数，提高数据相关性和多样性
TAG_TO_AMAP_TYPES: dict[str, str] = {
    # 中式 - 需要配合关键词搜索
    "火锅":   "050100|050900",  # 中餐厅 + 其他餐饮（需keywords="火锅"）
    "川菜":   "050100",         # 中餐厅（可配合keywords="川菜"）
    "粤菜":   "050100",         # 中餐厅
    "湘菜":   "050100",         # 中餐厅
    "烧烤":   "050100|050900",  # 中餐厅 + 其他餐饮（需keywords="烧烤"）
    "中餐":   "050100",         # 中餐厅
    "面食":   "050100|050300",  # 中餐厅 + 快餐（含面馆）
    "小吃":   "050300|050400",  # 快餐 + 小吃快餐
    # 日韩
    "日料":   "050200",         # 外国餐厅（含日本料理）
    "韩餐":   "050200",         # 外国餐厅（含韩国料理）
    # 西式
    "西餐":   "050200",         # 外国餐厅（含西餐）
    "快餐":   "050300",         # 快餐
    "汉堡":   "050300",         # 快餐
    # 饮品甜品 - typecode足够精确
    "咖啡":   "050500",         # 咖啡厅
    "奶茶":   "050500|050700",  # 咖啡厅 + 冷饮店
    "饮品":   "050500|050600|050700",  # 咖啡厅 + 茶座 + 冷饮店
    "甜品":   "050800",         # 甜品点
    "面包":   "050800",         # 甜品点（含烘焙）
    # 东南亚
    "东南亚": "050200",         # 外国餐厅
    # 其他
    "素食":   "050100|050900",  # 中餐厅 + 其他餐饮
    "海鲜":   "050100|050200",  # 中餐厅 + 外国餐厅
}

# ── 需要关键词搜索的标签映射 ──
# 对于typecode粒度不足的标签，使用keywords参数精确定位
TAG_TO_KEYWORDS: dict[str, str] = {
    # 中式 - 精确菜系
    "火锅":   "火锅",
    "烧烤":   "烧烤",
    "串串":   "串串",
    "麻辣烫": "麻辣烫",
    # 西式
    "西餐":   "西餐|牛排|披萨|意大利",  # 扩展关键词
    "快餐":   "快餐|汉堡|炸鸡|肯德基|麦当劳",
    # 日韩
    "韩餐":   "韩国料理|韩式|烤肉|韩国",
    "日料":   "日本料理|日式|寿司|拉面|日本",
    # 饮品甜品
    "咖啡":   "咖啡|星巴克|瑞幸|漫咖啡",
    "奶茶":   "奶茶|喜茶|奈雪|茶颜|霸王茶姬|古茗|蜜雪冰城",  # 扩展品牌词
    "饮品":   "饮品|冷饮|茶饮|柠檬茶|果茶",
    "甜品":   "甜品|蛋糕|烘焙|面包房|甜点|冰淇淋|DQ",
    "面包":   "面包|烘焙|面包房|蛋糕",
    # 面食小吃
    "面食":   "面|面条|拉面|米粉|米线|饺子|馄饨|兰州拉面",  # 扩展面类
    "小吃":   "小吃|早餐|包子|煎饼|烧烤|麻辣烫|冒菜",  # 广义小吃
    # 特色
    "东南亚": "泰国|越南|印度|咖喱|冬阴功|东南亚",
    "海鲜":   "海鲜|龙虾|螃蟹|贝类|鱼鲜",
}


def get_amap_types_for_tags(user_tags: list[str]) -> str:
    """
    根据用户标签列表，返回高德API的types参数。
    策略：收集所有匹配的typecode，去重后用|连接。
    若无匹配或标签为空，返回默认值"050000"（餐饮服务大类）。
    """
    if not user_tags:
        return "050000"

    typecode_set: set[str] = set()
    for tag in user_tags:
        if tag in TAG_TO_AMAP_TYPES:
            codes = TAG_TO_AMAP_TYPES[tag].split("|")
            typecode_set.update(codes)

    if not typecode_set:
        return "050000"

    return "|".join(sorted(typecode_set))


def get_keywords_for_tags(user_tags: list[str]) -> str | None:
    """
    根据用户标签列表，返回高德API的keywords参数（用于精确搜索）。
    仅对typecode粒度不足的标签返回关键词，其他返回None。
    多个标签时用|连接（高德支持多关键字）。
    """
    if not user_tags:
        return None

    keywords_list = []
    for tag in user_tags:
        if tag in TAG_TO_KEYWORDS:
            keywords_list.append(TAG_TO_KEYWORDS[tag])

    if not keywords_list:
        return None

    return "|".join(keywords_list)

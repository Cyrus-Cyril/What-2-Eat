"""
餐馆数据结构定义
所有模块都用这个统一格式传递餐馆数据
"""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Restaurant:
    restaurant_id: str       # 高德POI的唯一ID
    name: str                # 餐馆名称
    category: str            # 类别（type 路径最后一段），如"川菜"、"面食"
    distance_m: int          # 距用户位置的距离（米）
    rating: float            # 评分（0~5），没有评分则为0.0
    avg_price: float         # 人均消费（元），没有则为0.0
    address: str             # 地址
    latitude: float          # 纬度
    longitude: float         # 经度
    amap_type_path: str = ""  # 高德 type 完整路径，如"餐饮服务;中餐厅;川菜馆"，用于多段匹配
    amap_tags: str = ""       # 高德 business.tag 原始字符串，如"辣味,家常菜"，用于 taste/scene 标签

    def to_dict(self) -> dict:
        """转成字典，方便传给后端或存入数据库"""
        return asdict(self)

"""
config.py
集中管理配置，不把 Key 散落在各个文件里
"""

# 高德地图 API Key
AMAP_API_KEY = "6f38295e3f0fe606c75ea136b154db33"

# 周边搜索接口地址
AMAP_SEARCH_URL = "https://restapi.amap.com/v5/place/around"

# 餐饮类别代码（高德分类，050000代表所有餐饮）
RESTAURANT_TYPE_CODE = "050000"

# 默认搜索半径（米）
DEFAULT_RADIUS = 1000

# 每次最多返回的餐馆数量
DEFAULT_PAGE_SIZE = 20

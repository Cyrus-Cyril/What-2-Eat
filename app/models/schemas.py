"""
app/models/schemas.py
Pydantic 模型 —— 定义前后端接口的请求体与响应体结构
"""
from pydantic import BaseModel, Field


# ── 推荐接口 ──────────────────────────────────────────────

class RecommendRequest(BaseModel):
    user_id: str | None = Field(default=None, description="用户标识（数据库就绪后必填）")
    longitude: float = Field(description="用户当前经度（GCJ-02）", examples=[114.35968])
    latitude: float = Field(description="用户当前纬度（GCJ-02）", examples=[30.52878])
    radius: int = Field(default=1000, ge=50, le=50000, description="搜索半径（米）")
    max_count: int = Field(default=20, ge=1, le=50, description="最多返回餐馆数")
    budget_min: float | None = Field(default=None, ge=0, description="最低预算（元）")
    budget_max: float | None = Field(default=None, ge=0, description="最高预算（元）")
    taste: str | None = Field(default=None, description="口味偏好（如川菜、火锅）")
    max_distance: int | None = Field(default=None, ge=50, description="最大可接受距离（米）")
    people_count: int | None = Field(default=None, ge=1, description="就餐人数")


class RestaurantOut(BaseModel):
    restaurant_id: str = Field(description="高德POI唯一标识")
    name: str = Field(description="餐馆名称")
    category: str = Field(description="餐馆类别")
    distance_m: int = Field(description="距用户距离（米）")
    rating: float = Field(description="平台评分 0.0~5.0")
    avg_price: float = Field(description="人均消费（元）")
    address: str = Field(description="详细地址")
    latitude: float = Field(description="纬度（GCJ-02）")
    longitude: float = Field(description="经度（GCJ-02）")
    score: float = Field(default=0.0, description="推荐综合评分 0~1")
    reason: str = Field(default="", description="推荐理由说明")


class RecommendResponse(BaseModel):
    code: int = Field(default=0, description="状态码 0=成功 1=无结果 -1=异常")
    message: str = Field(default="ok", description="状态说明")
    data: list[RestaurantOut] = Field(default_factory=list, description="推荐餐馆列表")
    total: int = Field(default=0, description="结果总数")


# ── 反馈接口 ──────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    user_id: str = Field(description="用户标识")
    restaurant_id: str = Field(description="餐馆ID")
    rating: int = Field(ge=1, le=5, description="满意度评分 1~5")
    chosen: bool = Field(default=True, description="是否实际选择了该餐馆")


class FeedbackResponse(BaseModel):
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="反馈已记录", description="状态说明")


# ── 历史记录接口 ──────────────────────────────────────────

class HistoryItem(BaseModel):
    query_id: str = Field(description="查询编号")
    restaurant_name: str = Field(description="餐馆名称")
    category: str = Field(description="类别")
    distance_m: int = Field(description="距离")
    avg_price: float = Field(description="人均价格")
    score: float = Field(description="推荐评分")
    created_at: str = Field(description="推荐时间")


class HistoryResponse(BaseModel):
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="ok", description="状态说明")
    data: list[HistoryItem] = Field(default_factory=list, description="历史记录列表")
    total: int = Field(default=0, description="总记录数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页条数")


# ── 健康检查 ──────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="服务状态")
    version: str = Field(default="0.1.0", description="API版本")

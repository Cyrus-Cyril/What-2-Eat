"""
app/models/schemas.py
Pydantic 模型 —— 定义前后端接口的请求体与响应体结构
"""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


# ── 推荐接口 ──────────────────────────────────────────────

class ExplainScores(BaseModel):
    distance: float = Field(default=0.0)
    price: float = Field(default=0.0)
    rating: float = Field(default=0.0)
    tag: float = Field(default=0.0)


class DimensionDetail(BaseModel):
    dimension: str = Field(description="维度名称，如：地理位置")
    detail: str = Field(description="具体说明，如：步行5分钟内")
    score_impact: Literal["high", "medium", "low"] = Field(description="影响等级")


class ReasoningLogic(BaseModel):
    primary_factor: str = Field(description="首要决策因素")
    secondary_factor: str = Field(default="", description="次要决策因素")


class ExplainData(BaseModel):
    scores: ExplainScores = Field(default_factory=ExplainScores)
    matched_tags: list[str] = Field(default_factory=list)
    reason_hint: list[str] = Field(default_factory=list)
    summary: str | None = Field(default=None, description="一句话推荐理由")
    reasoning_logic: ReasoningLogic | None = Field(default=None, description="决策逻辑")
    match_details: list[DimensionDetail] = Field(default_factory=list, description="各维度评分解释")
    ai_speech: str | None = Field(default=None, description="AI生成的完整解释话术")


class RecommendRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: str | None = Field(default=None, description="用户标识")
    query: str | None = Field(default=None, description="自然语言输入（如『想吃麻辣火锅』）")
    longitude: float = Field(default=114.362, description="用户当前经度（GCJ-02）", examples=[114.35968])
    latitude: float = Field(default=30.532, description="用户当前纬度（GCJ-02）", examples=[30.52878])
    radius: int = Field(default=1000, ge=50, le=50000, description="搜索半径（米）")
    max_count: int = Field(default=10, ge=1, le=50, description="最多返回餐馆数")
    budget_min: float | None = Field(default=None, ge=0, description="最低预算（元）")
    budget_max: float | None = Field(default=None, ge=0, description="最高预算（元）")
    taste: str | None = Field(default=None, description="口味偏好（如川菜、火锅）")
    max_distance: int | None = Field(default=None, ge=50, description="最大可接受距离（米）")
    people_count: int | None = Field(default=None, ge=1, description="就餐人数")
    # 内部字段：由 intent_parser.parse() 写入，不暴露给 API，不参与序列化
    intent: Any = Field(default=None, exclude=True, description="意图约束（内部传递，不序列化）")


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
    explain: ExplainData | None = Field(default=None, description="结构化解释数据（供 LLM 模块使用）")


class StructuredContext(BaseModel):
    intent_mode: str = Field(description="场景模式描述")
    core_tags: list[str] = Field(default_factory=list, description="核心关键词")
    adjusted_weights: dict[str, str] = Field(default_factory=dict, description="调整后的权重说明")


class ExplanationSystem(BaseModel):
    hello_voice: str = Field(description="全局意图综述话术")
    structured_context: StructuredContext = Field(description="结构化意图上下文")
    my_logic: dict | None = Field(default=None, description="推荐引擎执行的松弛策略（仅供前端调试/AI参考）")


# ── 面向前端的公开输出结构 ────────────────────────────────

class ExplanationOut(BaseModel):
    """面向前端的解释结构，不包含内部评分数据。"""
    summary: str | None = Field(default=None, description="一句话推荐理由")
    reasoning_logic: ReasoningLogic | None = Field(default=None, description="决策逻辑")
    match_details: list[DimensionDetail] = Field(default_factory=list, description="各维度评分解释")
    ai_speech: str | None = Field(default=None, description="AI生成的完整解释话术")


class RecommendationItem(BaseModel):
    """前端可见的单条推荐结果。"""
    restaurant_id: str = Field(description="高德POI唯一标识")
    restaurant_name: str = Field(description="餐馆名称")
    explanation: ExplanationOut | None = Field(default=None, description="解释结果")


class RecommendResponse(BaseModel):
    code: int = Field(default=0, description="状态码 0=成功 1=无结果 -1=异常")
    message: str = Field(default="ok", description="状态说明")
    explanation_system: ExplanationSystem | None = Field(default=None, description="全局解释系统")
    recommendations: list[RecommendationItem] = Field(default_factory=list, description="推荐餐馆列表")


# ── 反馈接口 ──────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    user_id: str = Field(description="用户标识")
    recommendation_id: str | None = Field(default=None, description="对应的推荐记录ID")
    restaurant_id: str = Field(description="餐馆ID")
    action_type: Literal["LIKE", "DISLIKE"] | None = Field(
        default=None,
        description="显式表态：LIKE=点赞，DISLIKE=踩（优先于 rating 派生）",
    )
    rating: int = Field(ge=1, le=5, description="满意度评分 1~5（若未指定 action_type，>=4 视为 LIKE，<=2 视为 DISLIKE）")
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

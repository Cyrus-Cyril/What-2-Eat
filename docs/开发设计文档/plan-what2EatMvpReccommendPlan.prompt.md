# Plan: What-2-Eat MVP 推荐系统开发计划

**目标**：在现有后端框架上，实现完整推荐流程——接收用户请求 → 评分排序 → 生成 explain 数据 → 返回结构化结果。LLM 解释模块接口预留，本期用规则生成兜底。

---

## 一、系统模块划分

```
┌─────────────────────────────────────────────────────────┐
│  API 层（app/api/）                                       │
│   routes.py  ← 入口，负责请求解析 + 响应格式化           │
├─────────────────────────────────────────────────────────┤
│  推荐层（app/services/）                                  │
│   recommender.py   ← 主流程编排（现有，改造）            │
│   intent_parser.py ← 新建，自然语言意图解析 (LLM)       │
│   scorer.py        ← 新建，各维度打分逻辑                │
│   explainer.py     ← 新建，生成 explain JSON             │
│   tag_mapper.py    ← 新建，category → tag 映射           │
   user_profile.py  ← 新建，用户画像与长期偏好计算         │
├─────────────────────────────────────────────────────────┤
│  数据层（app/db/ + app/models/）                          │
│   database.py      ← 新建，SQLAlchemy 引擎 + Session     │
│   orm_models.py    ← 新建，6 张表的 ORM 定义             │
│   crud.py          ← 新建，增删查改封装                  │
│   [保留] restaurant.py / schemas.py（现有）              │
├─────────────────────────────────────────────────────────┤
│  外部服务（app/services/ 现有）                           │
│   amap_client.py / data_cleaner.py / data_entry.py      │
│   mock_data.py     ← 新建，USE_MOCK=true 时替代地图API   │
└─────────────────────────────────────────────────────────┘
```

---

## 二、数据流设计

```
前端 POST /api/recommend
  │ { user_id, query, (可选)longitude, (可选)latitude, ... }
  ▼
routes.py → recommender.recommend(req)
  │
  ├─0─ intent_parser.parse(user_id, query, raw_params) → RecommendRequest
  │         ├─ 调用 LLM 解析 query 提取意图参数
  │         ├─ 获取用户历史偏好 get_user_profile(user_id)
  │         └─ 按优先级合并参数 (Query > Params > History > Default)
  │
  ├─1─ mock_data / amap_client → 获取候选餐厅列表 (list[dict])
  │
  ├─2─ tag_mapper.map(category) → 每个餐厅附加 matched_tags
  │
  ├─3─ scorer.calc_all(r, req) → 返回 ScoreDetail
  │         ├ distance_score = 1 - dist/max_dist
  │         ├ price_score    = exp(-|price - mid_budget| / tolerance)
  │         ├ rating_score   = rating / 5.0
  │         ├ tag_score      = Σ(tag_weight) / tag_count
  │         └ final_score    = 加权求和
  │
  ├─4─ 排序 + 截取 top_n
  │
  ├─5─ explainer.build(r, score_detail) → ExplainData
  │         { scores:{...}, matched_tags:[...], reason_hint:[...] }
  │
  ├─6─ crud.save_query(user_id, req) → 写 user_query 表
  │    crud.save_recommendations(query_id, results) → 写 recommendation 表
  │
  └─7─ 构造 RecommendResponse 返回前端
```

---

## 三、意图解析模块设计 (IntentParser)

### 3.1 核心逻辑与优先级策略

`IntentParser` 负责将模糊的自然语言转化为符合算法要求的 `RecommendRequest` 结构。

**参数合并优先级（从高到低）：**
1. **Query (LLM解析值)**：如果用户在文字中明确说了“50块左右”，则以此为准。
2. **Raw Params (前端透传值)**：如果文字没提，但前端由于定位获取到了经纬度或用户手动选了筛选框，以此为准。
3. **History (用户画像)**：文字和前端都没提，由后端查询数据库获取用户常用偏好。
4. **Default (系统默认值)**：上述均无，使用系统预设值（如 `radius=2000`）。

### 3.2 历史偏好接口设计 (伪代码)

```python
# app/services/user_profile.py

async def get_user_profile(user_id: str) -> dict:
    """
    通过聚合 interaction 表数据，获取用户的长期偏好特征
    """
    # 实际开发时使用 SQL 聚合计算，MVP阶段可返回 Mock 数据
    return {
        "user_id": user_id,
        "avg_budget_max": 80,    # 历史平均最高消费
        "preferred_tastes": ["辣", "火锅"], # 历史高频标签
        "avg_radius": 1500,      # 历史常搜半径
        "last_location": {"lng": 114.36, "lat": 30.53}
    }
```

### 3.3 LLM 调用与 Prompt 设计

**Prompt 模板：**
```text
你是一个餐饮意图解析助手。请从用户的提问中提取以下信息并以标准 JSON 格式输出。
1. budget_max: 用户能接受的最高价格（数字，若提到"很贵"设200，"便宜"设30，否则 null）
2. budget_min: 用户能接受的最低价格（数字，否则 null）
3. radius: 搜索范围（数字，单位米。如"附近"设1000，"很近"设500，"远一点"设3000，否则 null）
4. taste: 提取口味或菜系关键词（字符串数组，如 ["川菜", "火锅"]，否则 []）
5. scene: 提取场景（如 "聚餐", "约会"，否则 null）

用户文字："{query}"

输出要求：只输出 JSON，严禁任何额外解释。
```

**LLM 实现与 Fallback 策略：**
- **调用方式**：使用 `config.LLM_API_KEY` 发起异步 HTTP 请求。
- **超时设置**：3秒超时。若超时，该部分参数设为空，进入下一优先级。
- **解析失败**：若 LLM 返回非 JSON 格式，捕获异常并记录日志，返回空意图字典。

### 3.4 Python 类设计 

```python
# app/services/intent_parser.py

class IntentParser:
    DEFAULT_VALUES = {
        "longitude": 114.362, # 默认光谷
        "latitude": 30.532,
        "radius": 2000,
        "budget_min": 0,
        "budget_max": 100,
        "taste": []
    }

    async def parse(self, user_id, query, raw_params: dict) -> RecommendRequest:
        # Step 1: LLM 解析自然语言
        query_intent = await self._call_llm(query)
        
        # Step 2: 获取历史偏好
        history_profile = await get_user_profile(user_id)

        # Step 3: 多源参数合并 (注意优先级关系)
        final_params = {}
        
        # 1. 经纬度：前端传值 > 历史记录 > 默认值
        final_params["longitude"] = raw_params.get("longitude") or \
                                   history_profile.get("last_location", {}).get("lng") or \
                                   self.DEFAULT_VALUES["longitude"]
        final_params["latitude"] = raw_params.get("latitude") or \
                                  history_profile.get("last_location", {}).get("lat") or \
                                  self.DEFAULT_VALUES["latitude"]

        # 2. 预算/范围：Query解析 > 前端传值 > 历史习惯 > 默认值
        for key in ["budget_min", "budget_max", "radius"]:
             final_params[key] = query_intent.get(key) or \
                                raw_params.get(key) or \
                                history_profile.get(f"avg_{key}") or \
                                self.DEFAULT_VALUES[key]

        # 3. 口味：Query解析 + 前端传值 + 历史标签 (取并集)
        taste_set = set(query_intent.get("taste", []))
        if raw_params.get("taste"): taste_set.add(raw_params["taste"])
        if not taste_set: # 如果前两者都无，用历史
            taste_set.update(history_profile.get("preferred_tastes", []))
        
        final_params["taste"] = list(taste_set)
        
        return RecommendRequest(user_id=user_id, **final_params)
```

### 3.5 示例输入输出

| 输入 (Query + Params) | 历史 (History) | 输出 (RecommendRequest) | 说明 |
| :--- | :--- | :--- | :-- |
| "想吃点便宜的川菜" + `{}` | `{avg_budget: 80}` | `{budget_max: 30, taste: ["川菜"]}` | Query 覆盖了历史高预算 |
| "附近有什么好吃的" + `{budget_max: 150}` | `{preferred_tastes: ["火锅"]}` | `{radius: 1000, budget_max: 150, taste: ["火锅"]}` | 结合了前端传值和历史偏好 |
| "随便推荐个" + `{}` | `{}` | `{radius: 2000, budget_max: 100, taste: []}` | 全部回退到系统默认值 |

---

## 四、数据库设计

### 3.1 restaurant（餐厅缓存表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | 高德 POI ID |
| `name` | TEXT NOT NULL | 餐厅名称 |
| `category` | TEXT | 高德原始分类（如"中餐厅;川菜"） |
| `address` | TEXT | 地址 |
| `latitude` | REAL | 纬度 |
| `longitude` | REAL | 经度 |
| `rating` | REAL DEFAULT 0 | 评分 0~5 |
| `avg_price` | REAL DEFAULT 0 | 人均消费（元） |
| `updated_at` | TEXT | 最后更新时间（ISO8601） |

> 作用：缓存高德结果，避免重复调用；tag_score 依赖 category 字段。

### 3.2 user_query（查询记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT | 用户标识（匿名可为随机串） |
| `longitude` | REAL | 请求时位置经度 |
| `latitude` | REAL | 请求时位置纬度 |
| `radius` | INTEGER | 搜索半径（米） |
| `budget_min` | REAL | 最低预算（NULL=未填） |
| `budget_max` | REAL | 最高预算（NULL=未填） |
| `taste` | TEXT | 口味偏好（NULL=未填） |
| `created_at` | TEXT | 查询时间 |

### 3.3 recommendation（推荐记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | UUID |
| `query_id` | TEXT FK→user_query.id | 所属查询 |
| `restaurant_id` | TEXT | 餐厅ID（不强制FK，高德ID可能未入库） |
| `restaurant_name` | TEXT | 冗余存名称，方便展示 |
| `rank` | INTEGER | 排名（1=第一） |
| `final_score` | REAL | 最终综合评分 |
| `score_distance` | REAL | 距离分 |
| `score_price` | REAL | 价格分 |
| `score_rating` | REAL | 评分分 |
| `score_tag` | REAL | 标签分 |
| `matched_tags` | TEXT | JSON数组字符串，如 `["川菜","辣"]` |
| `reason_hint` | TEXT | JSON数组字符串，如 `["评分较高"]` |
| `explain_json` | TEXT | 完整 explain JSON 字符串 |
| `created_at` | TEXT | 记录时间 |

### 3.4 feedback（反馈表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT | 用户标识 |
| `recommendation_id` | TEXT FK→recommendation.id | 对应推荐记录 |
| `restaurant_id` | TEXT | 餐厅ID（冗余，方便聚合） |
| `rating` | INTEGER | 满意度 1~5 |
| `chosen` | INTEGER | 是否实际去了（1/0） |
| `created_at` | TEXT | 反馈时间 |

---

## 四、SQL 文件设计

**输出文件结构：**
```
backend/
└── sql/
    ├── schema.sql    ← 建表语句（含 DROP IF EXISTS，可反复执行）
    └── seed.sql      ← 测试数据（10家餐厅 + 标签映射 + 1条查询示例）
```

**schema.sql 需包含：**
- `CREATE TABLE IF NOT EXISTS restaurant (...)`
- `CREATE TABLE IF NOT EXISTS user_query (...)`
- `CREATE TABLE IF NOT EXISTS recommendation (...)`
- `CREATE TABLE IF NOT EXISTS feedback (...)`
- 对 `user_query.user_id`、`recommendation.query_id` 建索引

**seed.sql 需包含：**
- 10 家餐厅（覆盖川菜/粤菜/火锅/快餐/日料等分类，含坐标/评分/价格）
- 坐标基准：武汉光谷（lng=114.36, lat=30.53）附近

---

## 五、推荐逻辑设计（scorer.py）

### 5.1 各维度打分公式

**距离分** `distance_score`：
$$DistanceScore = \max\left(0,\ 1 - \frac{distance\_m}{max\_dist}\right)$$
- `max_dist` = `req.max_distance` 若有填写，否则用 `req.radius`

**价格分** `price_score`：
$$PriceScore = e^{-\frac{|price - mid\_budget|}{tolerance}}$$
- `mid_budget` = `(budget_min + budget_max) / 2`
- `tolerance` = `(budget_max - budget_min) / 2`，最小值设 10 防除零
- 若用户未填预算：`price_score = 0.5`（中性分，不奖不惩）

**评分分** `rating_score`：
$$RatingScore = \frac{rating}{5.0}$$
- 若 rating == 0（无评分）：`rating_score = 0.4`（较低中性值）

**标签分** `tag_score`：
- 从 `tag_mapper` 获取该餐厅的 tag 列表（从 category 映射）
- 用户有 `taste` 时：完全匹配 → 1.0，部分匹配 → 0.6，无匹配 → 0.0
- 用户无 `taste` 时：`tag_score = 0.5`

**最终评分**（权重之和 = 1.0）：
$$FinalScore = 0.30 \cdot D + 0.25 \cdot P + 0.25 \cdot R + 0.20 \cdot T$$

### 5.2 explain 数据生成规则（explainer.py）

`reason_hint` 按优先级取最多3条：

| 条件 | hint 文字 |
|------|-----------|
| `distance_m ≤ 300` | `"步行5分钟内"` |
| `300 < distance_m ≤ 800` | `"步行可达"` |
| `rating ≥ 4.5` | `"口碑极佳"` |
| `4.0 ≤ rating < 4.5` | `"评分较高"` |
| `price_score ≥ 0.8` | `"价格非常合适"` |
| `0.6 ≤ price_score < 0.8` | `"价格适中"` |
| `tag_score ≥ 0.8` | `f"完全符合「{taste}」口味"` |
| `0.5 ≤ tag_score < 0.8` | `"符合口味偏好"` |

---

## 六、接口设计

### POST /api/recommend

**请求：**
```json
{
  "user_id": "u001",
  "longitude": 114.35968,
  "latitude": 30.52878,
  "radius": 1000,
  "max_count": 5,
  "budget_min": 20.0,
  "budget_max": 60.0,
  "taste": "川菜",
  "max_distance": 1000
}
```

**响应（新增 explain 字段）：**
```json
{
  "code": 0,
  "message": "ok",
  "total": 3,
  "data": [
    {
      "restaurant_id": "B001...",
      "name": "老成都川菜馆",
      "category": "川菜",
      "distance_m": 320,
      "rating": 4.6,
      "avg_price": 45.0,
      "address": "光谷步行街...",
      "latitude": 30.532,
      "longitude": 114.362,
      "score": 0.823,
      "reason": "步行可达；口碑极佳；完全符合「川菜」口味",
      "explain": {
        "scores": {
          "distance": 0.68,
          "price": 0.87,
          "rating": 0.92,
          "tag": 1.0
        },
        "matched_tags": ["川菜", "辣"],
        "reason_hint": ["步行可达", "口碑极佳", "完全符合「川菜」口味"]
      }
    }
  ]
}
```

> `reason` 保持原有字符串（规则拼接），`explain` 是结构化数据供 LLM 模块使用。  
> `explain.scores` 的四个 key（`distance/price/rating/tag`）是与 LLM 模块的约定，**不可更改**。

### POST /api/feedback（改造，写库）

```json
{
  "user_id": "u001",
  "recommendation_id": "rec-uuid-xxx",
  "restaurant_id": "B001...",
  "rating": 4,
  "chosen": true
}
```

### GET /api/history（改造，读库）

```
GET /api/history?user_id=u001&page=1&page_size=10
```

---

## 七、项目目录结构（目标状态）

```
backend/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py          ← 改造：feedback写库，history读库
│   ├── db/                    ← 新建目录
│   │   ├── __init__.py
│   │   ├── database.py        ← 新建：SQLAlchemy engine/session
│   │   ├── orm_models.py      ← 新建：4张表ORM
│   │   └── crud.py            ← 新建：增删查改
│   ├── models/
│   │   ├── __init__.py
│   │   ├── restaurant.py      ← 保留（dataclass）
│   │   └── schemas.py         ← 改造：RestaurantOut新增explain字段
│   ├── services/
│   │   ├── __init__.py
│   │   ├── amap_client.py     ← 保留
│   │   ├── data_cleaner.py    ← 保留
│   │   ├── data_entry.py      ← 保留，新增 USE_MOCK 分支
│   │   ├── mock_data.py       ← 新建：10家测试餐厅数据
│   │   ├── recommender.py     ← 改造：接入scorer/explainer/crud
│   │   ├── scorer.py          ← 新建：打分逻辑
│   │   ├── explainer.py       ← 新建：explain生成
│   │   └── tag_mapper.py      ← 新建：category→tag映射
│   └── main.py                ← 改造：lifespan中执行建表
├── sql/
│   ├── schema.sql             ← 新建
│   └── seed.sql               ← 新建
├── tests/
│   ├── test_api_and_cleaner.py ← 保留
│   ├── test_backend.py         ← 保留
│   └── test_scorer.py          ← 新建：scorer单元测试
├── config.py                  ← 改造：新增 USE_MOCK / DB路径
└── requirements.txt           ← 改造：新增 sqlalchemy aiosqlite
```

---

## 八、开发步骤（按阶段，每步可独立验证）

### Step 1 — 依赖 & 配置扩展（30min）
- `requirements.txt` 新增 `sqlalchemy==2.0.x`、`aiosqlite==0.20.x`
- `config.py` 新增 `USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"`、`DB_PATH`
- **验证**：`pip install -r requirements.txt` 无报错

### Step 2 — 数据库层（2h）
- 编写 `backend/sql/schema.sql`：包含 `tag`, `restaurant`, `restaurant_tag`, `user`, `user_tag_preference`, `interaction`, `user_query`, `recommendation`, `feedback` 等表的建表语句。
- 编写 `backend/sql/seed.sql`：预置基础标签树（如：中餐 -> 川菜 -> 火锅）及 10 条测试餐厅数据。
- 编写 `app/db/database.py`：创建 async SQLAlchemy engine，提供 `get_db()` 依赖。
- 编写 `app/db/orm_models.py`：定义 ORM 模型及关联关系。
- `app/main.py` lifespan 中执行 `schema.sql` 建表。
- **验证**：启动服务，检查 `data/master.db` 已创建，用 DB Browser 验证表结构。

### Step 3 — 用户画像与标签系统 (1.5h)
- 编写 `app/services/user_profile.py`：实现长期偏好读取及反馈更新逻辑（Step 9 接入）。
- 编写 `app/services/tag_mapper.py`：实现 category 到 tag 的语义映射。
- **验证**：调用 `UserProfile.get_history_preference(user_id)` 能正确获取标签权重。

### Step 4 — IntentParser 与 Mock 数据集成 (1.5h)
- 编写 `app/services/intent_parser.py`：解析 Query 获取 `tag_preferences` 和 `weight_adjustment`。
- 扩展 `RecommendRequest` schema 包含权重调整。
- 编写 `app/services/mock_data.py`。

### Step 5 — scorer（1.5h）
- 编写 `app/services/scorer.py`，实现 `ScoreDetail` dataclass + `calc_all()` 函数
- 严格按第五节公式实现
- **验证**：编写 `tests/test_scorer.py`，构造5个边界用例（无预算/距离为0/无评分等）验证输出范围在 [0,1]

### Step 6 — explainer（1h）
- 编写 `app/services/explainer.py`，实现 `build_explain(r, score_detail, taste) -> ExplainData`
- `ExplainData` 字段严格对应格式：`scores / matched_tags / reason_hint`
- **验证**：单函数调用，检查输出 JSON 结构与设计文档一致

### Step 7 — schemas 改造（30min）
- `app/models/schemas.py` 的 `RestaurantOut` 新增 `explain: ExplainData` 字段
- 同步更新 `RecommendResponse`
- **验证**：`/docs` Swagger 页面能看到新字段

### Step 8 — recommender 改造（1.5h）
- 改造 `recommender.py` 主流程，按数据流设计串联：
  `get_candidate_restaurants` → tag_mapper → scorer → explainer → 排序
- 暂不接入数据库写入（Step 9 再加）
- **验证**：完整调用 `/api/recommend`，响应中每条结果包含 `explain` 字段

### Step 9 — crud & 推荐写库（1.5h）
- 编写 `app/db/crud.py`：`save_query()` / `save_recommendations()` / `get_history()` / `save_feedback()`
- `recommender.py` 调用 `crud.save_query` + `crud.save_recommendations`
- `routes.py` 的 `/feedback` 改为调用 `crud.save_feedback`
- `routes.py` 的 `/history` 改为调用 `crud.get_history`
- **验证**：调用推荐接口后，SQL 查询 `user_query` / `recommendation` 表有记录；调用 `/history` 能返回历史

### Step 10 — 端到端测试（1h）
- 更新 `tests/test_backend.py`，补充：
  - 推荐结果中 `explain` 字段结构断言
  - feedback 提交后 history 能查到
- **验证**：`USE_MOCK=true python tests/test_backend.py` 全部 PASS

---

## 附：并行开发说明

| Step | 依赖 | 可并行 |
|------|------|--------|
| Step 1 | 无 | — |
| Step 2 | Step 1 | 可与 Step 3/4 并行 |
| Step 3 | Step 1 | 可与 Step 2/4 并行 |
| Step 4 | Step 1 | 可与 Step 2/3 并行 |
| Step 5 | Step 4 | — |
| Step 6 | Step 4/5 | — |
| Step 7 | Step 6 | — |
| Step 8 | Step 3/5/6/7 | — |
| Step 9 | Step 2/8 | — |
| Step 10 | Step 9 | — |

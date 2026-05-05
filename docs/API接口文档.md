# 今天吃什么 - 后端 API 接口文档
---

## 1. 概述

| 项目 | 说明 |
|------|------|
| 框架 | FastAPI |
| 默认地址 | `http://localhost:8000` |
| API 文档（自动生成） | `http://localhost:8000/docs` |
| 数据格式 | JSON |
| 字符编码 | UTF-8 |
| CORS | 已开放所有来源（开发阶段） |

---

## 2. 接口列表

| 方法 | 路径 | 说明 |
|:----:|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/recommend` | 获取餐馆推荐 |
| POST | `/api/feedback` | 提交用餐反馈 |
| GET | `/api/history` | 查询历史记录 |

---

## 3. 接口详情

### 3.1 健康检查

```
GET /api/health
```

**响应示例：**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

### 3.2 获取餐馆推荐（核心接口）

```
POST /api/recommend
Content-Type: application/json
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|:----:|:----:|------|------|
| `user_id` | string | 否 | 用户标识 | `"u001"` |
| `longitude` | float | **是** | 用户当前经度（GCJ-02） | `114.35968` |
| `latitude` | float | **是** | 用户当前纬度（GCJ-02） | `30.52878` |
| `radius` | int | 否 | 搜索半径（米），默认1000 | `800` |
| `max_count` | int | 否 | 最多返回条数，默认20 | `10` |
| `budget_min` | float | 否 | 最低预算（元） | `20` |
| `budget_max` | float | 否 | 最高预算（元） | `60` |
| `taste` | string | 否 | 口味偏好 | `"川菜"` |
| `max_distance` | int | 否 | 最大可接受距离（米） | `2000` |
| `people_count` | int | 否 | 就餐人数 | `2` |

**请求示例：**
```json
{
  "user_id": "u001",
  "longitude": 114.35968,
  "latitude": 30.52878,
  "radius": 800,
  "max_count": 10,
  "budget_min": 20,
  "budget_max": 60,
  "taste": "川菜",
  "max_distance": 2000,
  "people_count": 2
}
```

**响应体 `recommendations[]` 中每条餐馆的字段（对前端公开）：**

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `restaurant_id` | string | 高德POI唯一标识 |
| `restaurant_name` | string | 餐馆名称 |
| `explanation` | object | 结构化解释（见下 `ExplanationOut`） |

`ExplanationOut`（对前端公开的解释结构）：

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `summary` | string|null | 一句话摘要（建议放卡片首行） |
| `reasoning_logic` | object|null | `primary_factor` / `secondary_factor`（用于展示核心决策点） |
| `match_details` | array | 每维度证据链（`dimension`/`detail`/`score_impact`） |
| `ai_speech` | string|null | 可选的 LLM 生成话术（详情页使用） |

**重要说明（对前端）：**
- 后端内部维护的完整解释数据（含 `scores`、`matched_tags`、`reason_hint` 等）属于内部字段，仅用于 LLM prompt、日志或入库，不保证对前端暴露或稳定。前端应仅依赖 `ExplanationOut` 中的字段。

**响应示例（对外最新结构）：**
```json
{
  "code": 0,
  "message": "ok",
  "explanation_system": {
    "hello_voice": "给你找了个火锅店，附近火锅不多，就扩到中餐川菜辣的啦，味道应该不赖哈！",
    "structured_context": {
      "intent_mode": "Scene C - 精准品类筛选",
      "core_tags": ["火锅"],
      "adjusted_weights": { "distance": "0.30", "price": "0.25", "rating": "0.25", "tag": "0.20" }
    },
    "my_logic": {
      "level": 2,
      "original_filter_tags": ["火锅"],
      "original_budget_max": 70,
      "budget_relaxed": false,
      "tags_generalized": true,
      "downgraded": false,
      "note": "附近「火锅」太少了，帮你扩展到了「中餐、川菜、辣」",
      "generalized_tags": ["中餐","川菜","辣"]
    }
  },
  "recommendations": [
    {
      "restaurant_id": "R009",
      "restaurant_name": "素食轩",
      "explanation": {
        "summary": "人均约35元，非常合适的中餐厅;素食",
        "reasoning_logic": {
          "primary_factor": "人均价格：人均约35元，非常合适",
          "secondary_factor": "用户口碑：评分4.1，口碑较好"
        },
        "match_details": [
          { "dimension": "地理位置", "detail": "步行可达", "score_impact": "low" },
          { "dimension": "人均价格", "detail": "人均约35元，非常合适", "score_impact": "high" },
          { "dimension": "用户口碑", "detail": "评分4.1，口碑较好", "score_impact": "high" }
        ],
        "ai_speech": "素食轩哈，人均35块真香，评分4.1口碑稳！虽然位置一般咯，但性价比拉满吧！"
      }
    }
  ]
}
```

**状态码说明：**

| code | 含义 |
|:----:|------|
| `0` | 成功 |
| `1` | 无结果（附近找不到餐馆） |
| `-1` | 异常（接口调用失败等） |

---

## 4.1 解释系统扩展说明（新增）

从 2026-05-04 起，推荐接口支持可选的解释系统返回，前端可通过 `RecommendResponse` 的 `explanation_system` 字段开启/解析：

 - `explanation_system`（可选）：全局意图综述，包含：
   - `hello_voice`：向用户展示的自然语言综述（字符串），面向前端展示（非内部 prompt 字段名）
   - `structured_context`：结构化上下文，字段包括 `intent_mode`, `core_tags`, `adjusted_weights`
   - `my_logic`：可选的松弛/降级策略摘要（对象），用于前端显示系统在筛选过程中所做的放宽或泛化说明

 - `recommendations[][].explanation`：对前端公开的解释（`ExplanationOut`），只包含 `summary`/`reasoning_logic`/`match_details`/`ai_speech`。
  后端仍保留内部完整的 `explain`（含 `scores`/`matched_tags`/`reason_hint` 等），但这些字段仅用于内部处理、LLM prompt 或入库，不保证对前端暴露或长期稳定，前端应避免依赖这些内部字段。

前端渲染建议：
- 卡片摘要优先展示 `explain.summary`，次要展示 `reason_hint`；
 - 详情弹窗展示 `match_details` 的证据链，并在可用时展示 `ai_speech`；
- 若 `explanation_system.structured_context.fallback_from_hard_filter` 为真，展示相应提示说明系统已将硬过滤降级为软增强。

### 3.3 提交用餐反馈

```
POST /api/feedback
Content-Type: application/json
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|:----:|:----:|------|
| `user_id` | string | **是** | 用户标识 |
| `restaurant_id` | string | **是** | 餐馆ID |
| `rating` | int | **是** | 满意度评分 1~5 |
| `chosen` | bool | 否 | 是否实际选择了该餐馆，默认true |

**请求示例：**
```json
{
  "user_id": "u001",
  "restaurant_id": "B0012345ABC",
  "rating": 4,
  "chosen": true
}
```

**响应示例：**
```json
{
  "code": 0,
  "message": "反馈已记录"
}
```

---

### 3.4 查询历史记录

```
GET /api/history?user_id=u001&page=1&page_size=20
```

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|:----:|:----:|------|
| `user_id` | string | **是** | 用户标识 |
| `page` | int | 否 | 页码，默认1 |
| `page_size` | int | 否 | 每页条数，默认20 |

**响应体 `data[]` 中每条记录：**

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `query_id` | string | 查询编号 |
| `restaurant_name` | string | 餐馆名称 |
| `category` | string | 类别 |
| `distance_m` | int | 距离（米） |
| `avg_price` | float | 人均价格 |
| `score` | float | 推荐评分 |
| `created_at` | string | 推荐时间 |

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

> ⚠️ 当前版本历史记录返回空，待数据库就绪后由5号成员联调接入。

---

## 4. 前端调用示例（JavaScript fetch）

```javascript
// 获取推荐
const res = await fetch('http://localhost:8000/api/recommend', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    longitude: 114.35968,
    latitude: 30.52878,
    radius: 800,
    max_count: 10,
    budget_min: 20,
    budget_max: 60,
    taste: '川菜'
  })
});
const data = await res.json();
console.log(data.data);  // 推荐列表
```

---

## 5. 变更记录

| 版本 | 日期 | 变更 |
|:----:|------|------|
| v0.1.0 | 2026-05-02 | 初始版本，完成 recommend/feedback/history/health 四个接口定义 |

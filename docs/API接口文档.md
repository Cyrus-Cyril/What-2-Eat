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

| 方法 | 路径 | 标签 | 说明 |
|:----:|------|------|------|
| GET  | `/api/health`          | 系统 | 健康检查 |
| POST | `/api/nearby`          | 预取 | 周边餐厅预取（写入缓存） |
| POST | `/api/recommend`       | 推荐 | 智能推荐（支持自然语言+结构化参数） |
| POST | `/api/preset-recommend`| 推荐 | 预设偏好推荐（无 LLM，基于用户 profile） |
| POST | `/api/feedback`        | 反馈 | 提交用餐反馈 |
| GET  | `/api/history`         | 历史 | 查询历史推荐记录 |

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
  "version": "0.2.0"
}
```

---

### 3.2 周边餐厅预取

```
POST /api/nearby
Content-Type: application/json
```

在用户尚未发起推荐请求时，由前端提前调用。后端从高德 API 拉取附近餐厅数据并写入 Redis（TTL=600s）及 MySQL，使后续推荐请求直接命中缓存，降低响应延迟。

**请求体：**

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|:----:|:----:|:----:|------|
| `longitude` | float | **是** | — | 用户当前经度（GCJ-02） |
| `latitude`  | float | **是** | — | 用户当前纬度（GCJ-02） |
| `radius`    | int   | 否 | `1000` | 搜索半径（米），范围 50~50000 |
| `max_count` | int   | 否 | `20`   | 最多返回餐馆数，范围 1~100 |

**请求示例：**
```json
{
  "longitude": 114.35968,
  "latitude": 30.52878,
  "radius": 1000,
  "max_count": 20
}
```

**响应体：**

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `code`        | int    | 状态码，0=成功，1=无结果 |
| `message`     | string | 状态说明 |
| `count`       | int    | 返回餐厅数量 |
| `source`      | string | 数据来源（`api` / `cache` / `db`） |
| `restaurants` | array  | 周边餐厅列表（见下表） |

`restaurants[]` 每项字段：

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `restaurant_id` | string | 高德 POI 唯一标识 |
| `name`          | string | 餐馆名称 |
| `category`      | string | 餐馆类别 |
| `distance_m`    | int    | 距用户距离（米） |
| `rating`        | float  | 平台评分 0.0~5.0 |
| `avg_price`     | float  | 人均消费（元） |
| `address`       | string | 详细地址 |
| `latitude`      | float  | 纬度（GCJ-02） |
| `longitude`     | float  | 经度（GCJ-02） |

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "count": 2,
  "source": "api",
  "restaurants": [
    {
      "restaurant_id": "B0FFKQKNVV",
      "name": "老乡鸡",
      "category": "快餐",
      "distance_m": 210,
      "rating": 4.2,
      "avg_price": 25.0,
      "address": "武汉市武昌区XX路1号",
      "latitude": 30.5291,
      "longitude": 114.3604
    }
  ]
}
```

---

### 3.3 智能推荐（核心接口）

```
POST /api/recommend
Content-Type: application/json
```

支持两种输入模式：
- **自然语言模式**：填写 `query` 字段，后端调用 LLM 解析意图，自动推导其他参数；
- **结构化模式**：直接填写 `longitude`/`latitude` 等参数，跳过 LLM 解析。

两种模式可混用（`query` 优先，其余字段作为补充约束）。

**请求体：**

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|:----:|:----:|:----:|------|
| `user_id`      | string | 否 | `null`    | 用户标识（有则加载历史偏好） |
| `query`        | string | 否 | `null`    | 自然语言输入，如 `"想吃麻辣火锅，不超过60块"` |
| `longitude`    | float  | 否 | `114.362` | 用户当前经度（GCJ-02） |
| `latitude`     | float  | 否 | `30.532`  | 用户当前纬度（GCJ-02） |
| `radius`       | int    | 否 | `1000`    | 搜索半径（米），范围 50~50000 |
| `max_count`    | int    | 否 | `10`      | 最多返回餐馆数，范围 1~50 |
| `budget_min`   | float  | 否 | `null`    | 最低预算（元） |
| `budget_max`   | float  | 否 | `null`    | 最高预算（元） |
| `taste`        | string | 否 | `null`    | 口味偏好，如 `"川菜"`、`"火锅"` |
| `max_distance` | int    | 否 | `null`    | 最大可接受距离（米），最小 50 |
| `people_count` | int    | 否 | `null`    | 就餐人数，最小 1 |

**请求示例（自然语言模式）：**
```json
{
  "user_id": "u001",
  "query": "想吃麻辣火锅，预算70块以内，不要太远",
  "longitude": 114.35968,
  "latitude": 30.52878
}
```

**请求示例（结构化模式）：**
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

**响应体：**

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `code`               | int    | 状态码，0=成功，1=无结果，-1=异常 |
| `message`            | string | 状态说明 |
| `explanation_system` | object\|null | 全局意图综述（见下表） |
| `recommendations`    | array  | 推荐餐馆列表（见下表） |

`explanation_system` 字段：

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `hello_voice`       | string | LLM 生成的开场白，说明推荐逻辑（降级为规则模板时仍保证有值） |
| `structured_context`| object | 结构化意图上下文（见下） |
| `my_logic`          | object\|null | 推荐引擎执行的松弛/降级策略摘要，仅供前端调试参考 |

`explanation_system.structured_context` 字段：

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `intent_mode`      | string          | 场景描述，如 `"精准约束推荐"`、`"偏好导向推荐"`、`"综合评分推荐"` |
| `core_tags`        | array\<string\> | 核心标签，如 `["火锅", "辣"]` |
| `adjusted_weights` | object          | 各维度调整后权重，键为维度名，值为权重字符串，如 `{"distance": "0.40"}` |

`recommendations[]` 每项字段（对前端公开）：

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `restaurant_id`   | string       | 高德 POI 唯一标识 |
| `restaurant_name` | string       | 餐馆名称 |
| `explanation`     | object\|null | 结构化解释（见下表 `ExplanationOut`） |

`ExplanationOut` 字段（对前端公开的解释结构）：

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `summary`         | string\|null | 一句话摘要，建议放卡片首行 |
| `reasoning_logic` | object\|null | 核心决策逻辑，含 `primary_factor`（首要因素）和 `secondary_factor`（次要因素） |
| `match_details`   | array        | 各维度证据链，每项含 `dimension`（维度名）、`detail`（说明）、`score_impact`（`"high"`/`"medium"`/`"low"`） |
| `ai_speech`       | string\|null | LLM 生成的完整推荐话术，适合详情页展示 |

> **前端注意**：后端内部还维护 `scores`、`matched_tags`、`reason_hint` 等字段用于计算、入库和 LLM prompt，这些字段不对外保证稳定，前端应仅依赖 `ExplanationOut` 中的字段。

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "explanation_system": {
    "hello_voice": "找到啦！附近火锅不多，帮你扩展到川菜辣食了，味道应该差不多哈！",
    "structured_context": {
      "intent_mode": "精准约束推荐",
      "core_tags": ["火锅", "辣"],
      "adjusted_weights": {
        "distance": "0.30",
        "price": "0.30",
        "rating": "0.25",
        "tags": "0.15"
      }
    },
    "my_logic": {
      "tags_generalized": true,
      "note": "附近「火锅」太少，已扩展到「川菜、辣」"
    }
  },
  "recommendations": [
    {
      "restaurant_id": "B0FFKQKNVV",
      "restaurant_name": "巴蜀印象川菜馆",
      "explanation": {
        "summary": "步行可达的川菜馆",
        "reasoning_logic": {
          "primary_factor": "地理位置：步行可达",
          "secondary_factor": "人均价格：人均约45元，适中"
        },
        "match_details": [
          { "dimension": "地理位置", "detail": "步行可达", "score_impact": "high" },
          { "dimension": "人均价格", "detail": "人均约45元，适中", "score_impact": "medium" },
          { "dimension": "用户口碑", "detail": "评分4.3，口碑较好", "score_impact": "high" },
          { "dimension": "品类匹配", "detail": "完全符合「川菜、辣」口味", "score_impact": "high" }
        ],
        "ai_speech": "巴蜀印象哈，川味正宗，人均45块不贵，步行就能到，评分4.3口碑稳！"
      }
    }
  ]
}
```

---

### 3.4 预设偏好推荐

```
POST /api/preset-recommend
Content-Type: application/json
```

适用于首页「偏好推荐」卡片轮播。直接基于用户 profile 中的偏好标签、预算、距离等参数评分，**不调用 LLM**，响应速度更快。

**请求体：**

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|:----:|:----:|:----:|------|
| `user_id`             | string | 否 | `null`    | 用户标识 |
| `longitude`           | float  | 否 | `114.362` | 用户当前经度（GCJ-02） |
| `latitude`            | float  | 否 | `30.532`  | 用户当前纬度（GCJ-02） |
| `preference_tags`     | array  | 否 | `[]`      | 用户偏好标签，如 `["火锅", "川菜"]` |
| `budget_min`          | float  | 否 | `0`       | 最低预算（元） |
| `budget_max`          | float  | 否 | `100`     | 最高预算（元） |
| `distance_preference` | int    | 否 | `2000`    | 最大可接受距离（米），最小 50 |
| `spicy_preference`    | float  | 否 | `0.5`     | 辣度偏好，范围 0~1 |
| `sweet_preference`    | float  | 否 | `0.5`     | 甜度偏好，范围 0~1 |
| `healthy_preference`  | float  | 否 | `0.5`     | 健康饮食偏好，范围 0~1 |
| `favorites`           | array  | 否 | `[]`      | 收藏的餐馆名称列表 |
| `max_count`           | int    | 否 | `6`       | 最多返回餐馆数，范围 1~20 |

**请求示例：**
```json
{
  "user_id": "u001",
  "longitude": 114.35968,
  "latitude": 30.52878,
  "preference_tags": ["火锅", "川菜"],
  "budget_min": 20,
  "budget_max": 80,
  "distance_preference": 1500,
  "spicy_preference": 0.8,
  "max_count": 6
}
```

**响应体：**

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `code`            | int    | 状态码，0=成功，1=无结果，-1=异常 |
| `message`         | string | 状态说明 |
| `source`          | string | 数据来源（`api` / `mock`） |
| `recommendations` | array  | 推荐餐馆卡片列表（见下表） |

`recommendations[]` 每项字段：

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `id`          | string          | 唯一标识（高德 POI ID） |
| `name`        | string          | 餐馆名称 |
| `category`    | string          | 餐馆类别 |
| `tags`        | array\<string\> | 餐馆标签列表 |
| `avg_price`   | float           | 人均消费（元） |
| `rating`      | float           | 平台评分 0.0~5.0 |
| `distance_m`  | int             | 距用户距离（米） |
| `address`     | string          | 详细地址 |
| `reason`      | string          | 推荐理由文本 |
| `shared_tags` | array\<string\> | 与用户偏好匹配的标签 |
| `score`       | float           | 预设推荐评分（0~1） |

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "source": "api",
  "recommendations": [
    {
      "id": "B0FFKQKNVV",
      "name": "巴蜀印象川菜馆",
      "category": "川菜",
      "tags": ["川菜", "中餐", "辣"],
      "avg_price": 45.0,
      "rating": 4.3,
      "distance_m": 520,
      "address": "武汉市武昌区XX路1号",
      "reason": "符合你的川菜偏好，人均45元在预算内",
      "shared_tags": ["川菜", "辣"],
      "score": 0.87
    }
  ]
}
```

---

### 3.5 提交用餐反馈

```
POST /api/feedback
Content-Type: application/json
```

提交后，后端会：
1. 写入 `feedback` 表（同步）；
2. 若有显式表态（`action_type` 为 `LIKE`/`DISLIKE`），写入 `interaction` 黑白名单表；
3. 在后台异步更新用户标签偏好权重（不阻塞响应）。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|:----:|:----:|------|
| `user_id`           | string | **是** | 用户标识 |
| `restaurant_id`     | string | **是** | 餐馆 ID（高德 POI ID） |
| `rating`            | int    | **是** | 满意度评分 1~5 |
| `recommendation_id` | string | 否     | 对应的推荐记录 ID（便于数据分析，可不传） |
| `action_type`       | string | 否     | 显式表态：`"LIKE"` 或 `"DISLIKE"`（优先级高于 rating 派生） |
| `chosen`            | bool   | 否     | 是否实际选择了该餐馆，默认 `true` |

> **action_type 自动推导规则**（仅在 `action_type` 未传时生效）：`rating >= 4` → `LIKE`；`rating <= 2` → `DISLIKE`；否则不记录表态。

**请求示例：**
```json
{
  "user_id": "u001",
  "restaurant_id": "B0FFKQKNVV",
  "rating": 5,
  "action_type": "LIKE",
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

### 3.6 查询历史记录

```
GET /api/history?user_id=u001&page=1&page_size=20
```

**查询参数：**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|:----:|:----:|:----:|------|
| `user_id`   | string | **是** | —  | 用户标识 |
| `page`      | int    | 否     | `1`  | 页码，最小 1 |
| `page_size` | int    | 否     | `20` | 每页条数，范围 1~100 |

**响应体：**

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `code`      | int    | 状态码，0=成功 |
| `message`   | string | 状态说明 |
| `data`      | array  | 历史记录列表（见下表） |
| `total`     | int    | 总记录数 |
| `page`      | int    | 当前页码 |
| `page_size` | int    | 每页条数 |

`data[]` 每项字段：

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `query_id`        | string | 查询编号 |
| `restaurant_name` | string | 餐馆名称 |
| `category`        | string | 类别 |
| `distance_m`      | int    | 距离（米） |
| `avg_price`       | float  | 人均价格（元） |
| `score`           | float  | 推荐评分 |
| `created_at`      | string | 推荐时间（ISO 8601 格式） |

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "query_id": "3f5a2b1c-...",
      "restaurant_name": "巴蜀印象川菜馆",
      "category": "",
      "distance_m": 0,
      "avg_price": 0.0,
      "score": 0.82,
      "created_at": "2026-05-31T14:23:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

---

## 4. 通用状态码

| code | 含义 |
|:----:|------|
| `0`  | 成功 |
| `1`  | 无结果（如附近找不到餐馆） |
| `-1` | 异常（接口调用失败等） |

---

## 5. 前端调用示例（JavaScript fetch）

```javascript
// 1. 预取周边餐厅（页面加载时调用，提升后续推荐速度）
await fetch('http://localhost:8000/api/nearby', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ longitude: 114.35968, latitude: 30.52878, radius: 1000, max_count: 20 })
});

// 2. 自然语言推荐
const res = await fetch('http://localhost:8000/api/recommend', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: 'u001',
    query: '想吃火锅，预算60块以内',
    longitude: 114.35968,
    latitude: 30.52878
  })
});
const data = await res.json();
console.log(data.explanation_system.hello_voice); // 开场白
console.log(data.recommendations);               // 推荐列表

// 3. 预设偏好推荐（首页卡片）
const preset = await fetch('http://localhost:8000/api/preset-recommend', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: 'u001',
    longitude: 114.35968,
    latitude: 30.52878,
    preference_tags: ['川菜', '火锅'],
    budget_max: 80
  })
});

// 4. 提交反馈
await fetch('http://localhost:8000/api/feedback', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: 'u001',
    restaurant_id: 'B0FFKQKNVV',
    rating: 5,
    action_type: 'LIKE',
    chosen: true
  })
});
```

---

## 6. 变更记录

| 版本 | 日期 | 变更 |
|:----:|------|------|
| v0.1.0 | 2026-05-02 | 初始版本，完成 recommend / feedback / history / health 四个接口定义 |
| v0.2.0 | 2026-05-31 | 补充 nearby（预取）、preset-recommend（预设偏好推荐）两个接口；补充 feedback 中 action_type / recommendation_id 字段；修正推荐接口响应结构（ExplanationOut、explanation_system）；修正版本号；删除已不适用的内部字段说明 |

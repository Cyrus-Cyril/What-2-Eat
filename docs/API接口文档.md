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

**响应体 `data[]` 中每条餐馆的字段：**

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `restaurant_id` | string | 高德POI唯一标识 |
| `name` | string | 餐馆名称 |
| `category` | string | 餐馆类别（如"川菜"） |
| `distance_m` | int | 距用户距离（米） |
| `rating` | float | 平台评分 0.0~5.0 |
| `avg_price` | float | 人均消费（元） |
| `address` | string | 详细地址 |
| `latitude` | float | 纬度（GCJ-02） |
| `longitude` | float | 经度（GCJ-02） |
| `score` | float | 推荐综合评分 0~1 |
| `reason` | string | 推荐理由说明 |

**响应示例：**
```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "restaurant_id": "B0012345ABC",
      "name": "川味轩",
      "category": "川菜",
      "distance_m": 350,
      "rating": 4.5,
      "avg_price": 45.0,
      "address": "珞喻路123号",
      "latitude": 30.5312,
      "longitude": 114.3621,
      "score": 0.85,
      "reason": "距离仅350m,非常近；评分4.5分,口碑好；符合你的"川菜"口味偏好；人均¥45"
    }
  ],
  "total": 1
}
```

**状态码说明：**

| code | 含义 |
|:----:|------|
| `0` | 成功 |
| `1` | 无结果（附近找不到餐馆） |
| `-1` | 异常（接口调用失败等） |

---

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

# What-2-Eat 今天吃什么

基于位置与偏好的智能餐饮推荐系统

## ✨ 核心特性

- **双引擎推荐**：支持 LLM 自然语言查询 + 预设偏好快速推荐
- **智能标签匹配**：11个精选餐饮标签，100%高匹配率
- **动态数据源**：根据用户标签自动优化高德API搜索策略
- **多标签支持**：选择多个偏好时智能评分，不会稀释分数
- **实时位置服务**：基于高德地图周边搜索，支持距离/预算/口味多维筛选

## 🏗️ 项目结构

```
What-2-Eat/
├── backend/                     # 后端（FastAPI + Python）
│   ├── app/
│   │   ├── api/routes.py       # API 路由
│   │   ├── services/
│   │   │   ├── amap_client.py      # 高德地图 API 客户端
│   │   │   ├── preset_recommender.py  # 预设偏好推荐引擎 ⭐
│   │   │   ├── recommender.py       # LLM 推荐引擎
│   │   │   ├── tag_mapper.py        # 标签映射系统 ⭐
│   │   │   └── data_entry.py        # 数据获取与缓存
│   │   └── main.py             # 应用入口
│   └── config.py               # 配置文件
├── frontend/                    # 前端（Vue 3 + Vite）
│   └── src/
│       ├── views/
│       │   ├── HomeView.vue         # 首页（主推荐界面）
│       │   ├── AuthView.vue         # 注册/登录
│       │   └── ProfileView.vue      # 个人偏好设置
│       └── services/
│           └── auth.js              # 用户认证与状态管理
└── README.md
```

## 🚀 快速启动

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

访问 `http://localhost:8000/docs` 查看 API 文档。

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173` 使用前端界面。

### 环境配置（可选）

若使用 LLM 功能，创建 `.env` 文件：

```bash
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY 和 LLM_API_URL
```

## 🎯 推荐系统

### 两种推荐模式

| 模式 | 路由 | 特点 |
|------|------|------|
| **LLM 推荐** | `/api/recommend` | 支持自然语言查询，调用大模型解析意图 |
| **预设偏好** | `/api/preset-recommend` | 不调用 LLM，基于用户标签快速推荐 |

### 📌 预设偏好标签（11个）

**中式**: 火锅、烧烤、面食  
**外来**: 日料、韩餐、西餐、东南亚  
**快餐**: 快餐  
**饮品**: 咖啡、奶茶、饮品  

> 所有标签经过验证，匹配率 90%+，平均推荐分数 0.93+

## 🔧 技术栈

- **后端**: Python 3.13 + FastAPI + Redis 缓存
- **前端**: Vue 3 (Composition API) + Vite
- **地图服务**: 高德地图 V5 API
- **AI**: 可选接入大模型（支持多 Provider）

## 📦 主要依赖

后端: `fastapi`, `uvicorn`, `redis`, `httpx`, `pydantic`  
前端: `vue`, `vue-router`, `axios`

## 📝 开发说明

- 后端日志级别通过 `LOG_LEVEL` 环境变量控制
- 高德 API 数据默认缓存 5-30 分钟（根据搜索类型自动调整）
- 预设推荐支持关键词搜索 + 智能名称识别双重保障
- 前端已实现标签过滤机制，自动清理无效的历史偏好数据

## 🧪 压力测试

使用 Locust 进行并发压力测试：

```bash
cd backend
pip install locust

# 标准模式（LLM 意图解析 + AI 解释）
locust -f tests/load/locustfile_standard.py --headless -u 10 -r 2 --run-time 60s --host http://localhost:8000

# 极速模式（跳过 LLM，< 1s 返回）
locust -f tests/load/locustfile_fast.py --headless -u 10 -r 2 --run-time 60s --host http://localhost:8000

# Web UI 可视化（浏览器打开 http://localhost:8089）
locust -f tests/load/locustfile_standard.py --host http://localhost:8000

locust -f tests/load/locustfile_fast.py --host http://localhost:8000
```

### 10用户×60s 基准测试结果

| 模式 | 请求数 | 失败率 | 平均延迟 | P90 延迟 | RPS |
|------|--------|--------|----------|----------|-----|
| **极速模式** | 371 | 0% | 61ms | 83ms | 6.2 |
| **标准模式** | 120 | 0% | 3692ms | 6900ms | 1.8 |

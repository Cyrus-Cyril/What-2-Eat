# What-2-Eat 今天吃什么

基于位置与偏好的智能餐饮推荐系统

## 项目结构

```
What-2-Eat/
├── backend/                # 后端（FastAPI + Python）
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py       # API 路由（health / recommend / feedback / history）
│   │   ├── models/
│   │   │   ├── restaurant.py   # Restaurant dataclass（9字段）
│   │   │   └── schemas.py      # Pydantic 请求/响应模型
│   │   ├── services/
│   │   │   ├── amap_client.py  # 高德地图 V5 周边搜索 API
│   │   │   ├── data_cleaner.py # 原始数据清洗
│   │   │   ├── data_entry.py   # 数据入口（整合amap+cleaner）
│   │   │   └── recommender.py  # 推荐引擎（评分排序）
│   │   └── main.py             # FastAPI 应用入口
│   ├── tests/
│   │   ├── test_api_and_cleaner.py  # 数据层集成测试
│   │   └── test_backend.py          # 接口自动化测试（需启动服务）
│   ├── config.py               # 集中配置（支持环境变量覆盖）
│   └── requirements.txt        # Python 依赖
├── frontend/               # 前端（待开发）
├── docs/                   # 项目文档
│   ├── API接口文档.md
│   ├── 字段说明文档.md
│   ├── 推荐系统设计文档.md
│   └── 后端5月2日工作总结.md
└── README.md
```

## 快速启动

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

在运行服务前，若需要使用大模型（LLM）相关功能，请在项目根目录创建 `.env` 文件：

```bash
cp .env.example .env
# 编辑 .env 填入你的 LLM_API_KEY 和 LLM_API_URL
```

启动后访问 `http://localhost:8000/docs` 查看 API 文档。

### 前端

> 待开发，代码将放在 `frontend/` 目录。

## 后端环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AMAP_API_KEY` | 高德地图 API Key | 内置测试Key |
| `SERVER_HOST` | 服务监听地址 | `0.0.0.0` |
| `SERVER_PORT` | 服务端口 | `8000` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `LLM_API_KEY` | 大模型服务的 API Key（若使用） | 空 |
| `LLM_API_URL` | 大模型服务的请求地址（若使用） | 空 |

说明：仓库中提供了 [.env.example](./.env.example) 示例文件，开发者应复制为 `.env` 并填写真实值（不要将 `.env` 提交到远程仓库）。
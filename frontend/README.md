# What-2-Eat Frontend

Vue 3 + Vite 前端工作台，用于联调 `What-2-Eat` 后端推荐接口。

## 当前能力

- 输入推荐参数并调用 `POST /api/recommend`
- 检查后端健康状态 `GET /api/health`
- 展示 `explanation_system` 和每条推荐的结构化解释

## 环境变量

在 `frontend/` 目录下创建 `.env.local`：

```sh
VITE_API_BASE_URL=http://localhost:8000
```

未配置时，前端默认请求 `http://localhost:8000`。

## 启动方式

```sh
npm install
npm run dev
```

## 常用命令

```sh
npm run build
npm run test:unit
npm run test:e2e
npm run lint
```

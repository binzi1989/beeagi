# BeeAGI x Codex

BeeAGI 是一个受蜂群启发的多智能体编排平台，带桌面控制台。

## 核心角色

- **斥候 Scout**：环境侦察与结构化情报
- **工蜂 Worker**：计划优先执行任务
- **蠕虫 Worm**：吸收反馈并提出技能演化候选
- **蜂王 Queen**：候选晋升、灰度治理、回滚决策

## 当前包含内容

- **后端**：FastAPI 控制平面、影子回放、5% 灰度、进化闭环
- **桌面端**：Tauri + React，场景化工作台，对话式时间线，交付产物优先
- **LLM 页面**：运行时模型配置 + Token 用量统计

## 目录结构

- `backend/`：API、编排、测试
- `desktop/`：桌面 UI
- `docs/`：架构说明

## 快速启动

### 后端

```bash
cd backend
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 桌面端

```bash
cd desktop
npm install
npm run dev
```

## 关键接口

- `POST /tasks`
- `GET /tasks/{id}`
- `POST /tasks/{id}/feedback`
- `POST /tasks/{id}/auto-feedback`
- `GET /skills`
- `POST /skills/{id}/candidate`
- `POST /skills/{id}/promote`
- `POST /skills/{id}/rollback`
- `POST /skills/{id}/candidate/{candidate_id}/shadow-replay`
- `GET /skills/{id}/candidate/{candidate_id}/canary-status`
- `POST /evolution/auto-promote`
- `GET /evolution/events`
- `GET /evolution/candidate-audits`
- `GET /evolution/hardening-report`
- `GET /llm/config`
- `PUT /llm/config`
- `GET /llm/token-stats`

## 开源配套

- 许可证：`MIT`
- 贡献指南：[`CONTRIBUTING.md`](./CONTRIBUTING.md)
- 社区行为准则：[`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)
- 安全策略：[`SECURITY.md`](./SECURITY.md)
- CI：`.github/workflows/ci.yml`

## 安全提示

- 不要提交 `.env` 和 API Key。
- 生产环境请启用 `APP_CONTROL_PLANE_API_KEY`。

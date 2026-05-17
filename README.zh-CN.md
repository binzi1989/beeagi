# BeeAGI x Codex

[![CI](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml/badge.svg)](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

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

## 文档导航（中文）

- 项目总览：[`README.zh-CN.md`](./README.zh-CN.md)
- 后端说明：[`backend/README.zh-CN.md`](./backend/README.zh-CN.md)
- 桌面端说明：[`desktop/README.zh-CN.md`](./desktop/README.zh-CN.md)
- 快速上手：[`docs/quickstart.zh-CN.md`](./docs/quickstart.zh-CN.md)
- 发布说明（中文）：[`docs/releases/v0.1.0.zh-CN.md`](./docs/releases/v0.1.0.zh-CN.md)

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
- Issue 模板：`.github/ISSUE_TEMPLATE/`
- PR 模板：`.github/pull_request_template.md`

发布说明：

- 英文：[`v0.1.0`](./docs/releases/v0.1.0.md)
- 中文：[`v0.1.0（中文）`](./docs/releases/v0.1.0.zh-CN.md)

## 安全提示

- 不要提交 `.env` 和 API Key。
- 生产环境请启用 `APP_CONTROL_PLANE_API_KEY`。

## 社区协作建议

1. 报 Bug：使用 `Bug Report` 模板，附复现步骤与日志。  
2. 提需求：使用 `Feature Request` 模板，说明场景和预期收益。  
3. 提 PR：按模板补齐“用户影响 + 测试结果 + 截图（如有 UI 变更）”。

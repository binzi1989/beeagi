# BeeAGI x Codex

[![CI](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml/badge.svg)](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

面向真实交付的私有化蜂群智能体平台：任务规划、执行、反馈、自进化，全链路可追溯。

English docs: [README.md](./README.md)

## 项目价值

BeeAGI 融合三条主线：

- 论文中的四角色架构：Scout / Worker / Worm / Queen
- Codex 风格的“计划优先 + 工具边界 + 审计闭环”
- 反馈驱动的技能自进化（影子回放 + 灰度 + 回滚）

## 30 秒启动

1. 启动后端：

```bash
cd backend
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

2. 启动桌面端：

```bash
cd desktop
npm install
npm run dev
```

3. 在界面中选择场景并运行。

## 实物交付（重点）

系统现在支持“写入实物文件”，不是只给文字摘要。

- `coding`：交付完整可运行程序骨架（代码 + 测试 + README）
- `skills_factory`：交付 `SKILL.md` 技能包
- `office/research/debug/data/product/video_creator`：交付场景化报告及配套文件（如 SQL/CSV）

使用方式：

1. 打开任务输入的“高级设置”。
2. 配置“绑定本地交付目录”（例如 `D:\Bee2\deliverables`）。
3. 保持“允许写入实物文件”开启。
4. 运行任务后，在“交付产物”面板查看文件清单与绝对路径。

也可通过任务约束配置：

```json
{
  "workspaceBinding": {
    "targetDir": "D:/Bee2/deliverables",
    "allowWrite": true,
    "allowExecute": false
  }
}
```

## 核心 API

- `POST /tasks`
- `GET /tasks/{id}`
- `POST /tasks/{id}/feedback`
- `POST /tasks/{id}/auto-feedback`
- `POST /tasks/{id}/deliverables/open`
- `GET /tasks/{id}/deliverables/download`
- `GET /tasks/{id}/deliverables/archive`
- `GET /skills`
- `POST /skills/{id}/candidate`
- `POST /skills/{id}/promote`
- `POST /skills/{id}/rollback`
- `POST /skills/{id}/candidate/{candidate_id}/shadow-replay`
- `GET /skills/{id}/candidate/{candidate_id}/canary-status`
- `GET /evolution/events`
- `GET /evolution/pheromones`
- `POST /evolution/scout-patrol`
- `POST /evolution/auto-promote`
- `GET /evolution/candidate-audits`
- `GET /evolution/hardening-report`
- `GET /llm/config`
- `PUT /llm/config`
- `GET /llm/token-stats`

## 目录结构

- `backend/`：FastAPI 控制平面、智能体编排、测试
- `desktop/`：Tauri + React 桌面 GUI
- `docs/`：架构文档、发布说明、演示脚本、增长内容

## 开源协作

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)
- [SECURITY.md](./SECURITY.md)
- [Issue 模板](./.github/ISSUE_TEMPLATE)
- [PR 模板](./.github/pull_request_template.md)

## 发布说明

- [v0.2.0](./docs/releases/v0.2.0.md)
- [v0.2.0（中文）](./docs/releases/v0.2.0.zh-CN.md)
- [v0.1.0](./docs/releases/v0.1.0.md)
- [v0.1.0（中文）](./docs/releases/v0.1.0.zh-CN.md)

## 安全提示

- 不要提交 `.env` 或 API Key。
- 生产环境建议开启 `APP_CONTROL_PLANE_API_KEY`。

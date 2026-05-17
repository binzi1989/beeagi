# BeeAGI x Codex

[![CI](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml/badge.svg)](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

一个面向真实交付场景的私有化蜂群智能体平台：任务规划、执行、反馈、进化，全链路可追踪。

English docs: [README.md](./README.md)

## 项目价值

BeeAGI 融合了三件事：

- 论文中的四角色蜂群架构（Scout / Worker / Worm / Queen）
- Codex 风格的“计划优先 + 工具边界 + 可审计”
- 强反馈驱动的技能自进化（不是旁路日志）

## 30 秒快速演示

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

3. 在界面里：
- 选择 `编程场景`
- 输入目标、上下文、验收 JSON
- 点击 `一键跑完整流程`
- 查看“交付产物”和“对话式时间线”
- 提交反馈或执行自动反馈

你会看到：

- 任务链路：Scout -> Worker -> 交付结果
- 反馈链路：用户反馈 -> Worm 产出技能候选
- 治理链路：影子回放 -> 5% 灰度 -> 晋升/回滚

演示脚本：

- [30 秒脚本（英文）](./docs/demo/30s-demo-script.md)
- [30 秒脚本（中文）](./docs/demo/30s-demo-script.zh-CN.md)

## v0.2.0 已实现能力

- 场景化桌面工作台（编程/办公/研究/排障/数据/产品）
- 对话式时间线 + 交付产物优先交互
- LLM 配置与 Token 统计页面
- 影子回放评估器 + 真实 5% 灰度分配
- 候选技能晋升/回滚与审计记录
- 主动 Scout 信息素闭环：
  - 沉积（从上下文与信号生成）
  - 蒸发（时间衰减 + TTL）
  - 注入（Top-K 信息素进入 Worker 执行）
  - 奖惩（反馈反向更新信息素强度）
  - 巡检（历史任务主动采样）

## 核心 API

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
- `docs/`：架构、发布说明、演示脚本、开源增长材料

## 开源协作

- 贡献指南：[CONTRIBUTING.md](./CONTRIBUTING.md)
- 社区行为准则：[CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)
- 安全策略：[SECURITY.md](./SECURITY.md)
- Issue 模板：[`.github/ISSUE_TEMPLATE`](./.github/ISSUE_TEMPLATE)
- PR 模板：[`.github/pull_request_template.md`](./.github/pull_request_template.md)

## 发布说明

- [v0.2.0](./docs/releases/v0.2.0.md)
- [v0.2.0（中文）](./docs/releases/v0.2.0.zh-CN.md)
- [v0.1.0](./docs/releases/v0.1.0.md)
- [v0.1.0（中文）](./docs/releases/v0.1.0.zh-CN.md)

## GitHub 增长打法

- [GitHub 开源启动作战手册（中文）](./docs/growth/github-launch-playbook.zh-CN.md)

## 安全提示

- 不要提交 `.env` 或 API Key。
- 生产环境建议启用 `APP_CONTROL_PLANE_API_KEY`。

# BeeAGI x Codex

[![CI](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml/badge.svg)](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

Private-first swarm orchestration for real delivery work: task planning, execution, feedback, and controlled self-evolution.

Chinese docs: [README.zh-CN](./README.zh-CN.md)

## Why This Project

BeeAGI combines:

- Four-role swarm architecture (Scout / Worker / Worm / Queen)
- Codex-style plan-first execution and tool boundaries
- Human-in-the-loop governance for risky skill updates
- Auditable evolution with shadow replay + canary + rollback

## 30-Second Demo

1. Start backend:

```bash
cd backend
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

2. Start desktop:

```bash
cd desktop
npm install
npm run dev
```

3. In UI:
- Choose scenario `Coding`
- Fill goal + context + acceptance JSON
- Click `Run Full Workflow`
- Check deliverable panel and chat timeline
- Submit manual feedback or run auto-feedback

Expected behavior:

- Task chain: Scout -> Worker -> output
- Feedback chain: feedback -> Worm delta proposal
- Governance chain: shadow replay -> canary -> promote/rollback

## Physical Deliverables (New)

BeeAGI now writes concrete artifacts to disk instead of only showing summaries.

- `coding`: full runnable project scaffold (code + tests + README)
- `skills_factory`: `SKILL.md` package output
- `office/research/debug/data/product/video_creator`: scenario report files (+ companion files like SQL/CSV where relevant)

How to use:

1. Open **Advanced Settings** in the desktop UI.
2. Set **Bound Local Delivery Folder** (for example `D:\\Bee2\\deliverables`).
3. Keep **Allow Writing Artifacts** enabled.
4. Run a task. The deliverable panel shows file list + absolute paths.

You can also control this through `constraints.workspaceBinding`:

```json
{
  "workspaceBinding": {
    "targetDir": "D:/Bee2/deliverables",
    "allowWrite": true,
    "allowExecute": false
  }
}
```

Detailed script:

- [30s demo script (EN)](./docs/demo/30s-demo-script.md)
- [30s demo script (ZH)](./docs/demo/30s-demo-script.zh-CN.md)

## What Works in v0.2.0

- Scenario-driven desktop workflow (coding / office / research / debug / data / product)
- Chat-like timeline and deliverable-first interaction
- LLM config and token statistics console
- Evolution pulse telemetry (progress score, velocity score, role throughput, trend timeline)
- Shadow replay evaluator and real 5% canary allocator
- Candidate promotion/rollback with audit trail
- Active Scout pheromone loop:
  - deposit (from context/signals)
  - evaporation (time decay + ttl)
  - task injection (top-k pheromones into Worker)
  - feedback reward/punishment
  - patrol mode (historical sampling)

## Core APIs

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
- `GET /evolution/telemetry`
- `GET /evolution/pheromones`
- `POST /evolution/scout-patrol`
- `POST /evolution/auto-promote`
- `GET /evolution/candidate-audits`
- `GET /evolution/hardening-report`
- `GET /llm/config`
- `PUT /llm/config`
- `GET /llm/token-stats`

## Repo Layout

- `backend/` FastAPI control plane, orchestration services, tests
- `desktop/` Tauri + React GUI
- `docs/` architecture, releases, demo scripts, launch materials

## Open Source Collaboration

- Contributing: [CONTRIBUTING.md](./CONTRIBUTING.md)
- Code of Conduct: [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)
- Security policy: [SECURITY.md](./SECURITY.md)
- Issue templates: [`.github/ISSUE_TEMPLATE`](./.github/ISSUE_TEMPLATE)
- PR template: [`.github/pull_request_template.md`](./.github/pull_request_template.md)

## Release Notes

- [v0.2.0](./docs/releases/v0.2.0.md)
- [v0.2.0 (Chinese)](./docs/releases/v0.2.0.zh-CN.md)
- [v0.1.0](./docs/releases/v0.1.0.md)
- [v0.1.0 (Chinese)](./docs/releases/v0.1.0.zh-CN.md)

## Growth Playbook

- [GitHub launch playbook (Chinese)](./docs/growth/github-launch-playbook.zh-CN.md)

## Notes

- Do not commit `.env` or API keys.
- For production, enable `APP_CONTROL_PLANE_API_KEY`.

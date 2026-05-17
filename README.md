# BeeAGI x Codex

BeeAGI is a swarm-inspired multi-agent orchestration platform with a desktop control console.

## Core idea

- **Scout**: environment sensing and structured reconnaissance
- **Worker**: plan-first task execution
- **Worm**: feedback digestion and skill evolution proposal
- **Queen**: promotion, canary governance, and rollback

## What is included

- **Backend**: FastAPI control plane, evolution loop, shadow replay, canary allocator
- **Desktop**: Tauri + React scenario workspace with chat-style timeline and deliverable-first UX
- **LLM Console page**: runtime model config + token usage stats

## Repository layout

- `backend/` API, orchestration, tests
- `desktop/` desktop UI
- `docs/` architecture notes

## Quick start

### Backend

```bash
cd backend
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Desktop

```bash
cd desktop
npm install
npm run dev
```

## Key APIs

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

## Open source readiness

- License: `MIT`
- Contributing guide: [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- Code of conduct: [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)
- Security policy: [`SECURITY.md`](./SECURITY.md)
- CI workflow: `.github/workflows/ci.yml`

## Notes

- Do not commit `.env` or API keys.
- For production, enable `APP_CONTROL_PLANE_API_KEY`.

Chinese documentation: [`README.zh-CN.md`](./README.zh-CN.md)

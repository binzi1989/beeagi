# Backend Quick Start

## 1) Install

```bash
python -m pip install -e ".[dev]"
```

## 2) Run API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 3) Run Worker (optional for async tasks)

```bash
celery -A worker.celery_app.celery_app worker --loglevel=INFO
```

## 4) Run tests

```bash
pytest tests -q
```

## Environment Variables

- `APP_DATABASE_URL` (default: `sqlite:///./beeagi.db`)
- `APP_REDIS_URL`
- `APP_CONTROL_PLANE_API_KEY` (optional, enables write-endpoint auth)
- `APP_CONTROL_PLANE_API_KEY_HEADER` (default: `X-API-Key`)
- `APP_CORS_ALLOW_ORIGINS` (JSON array, includes Tauri/Vite local origins)
- `APP_CORS_ALLOW_METHODS` (JSON array, default includes `OPTIONS`)
- `APP_CORS_ALLOW_HEADERS` (JSON array)
- `APP_CORS_ALLOW_CREDENTIALS` (`true`/`false`)
- `APP_CELERY_ENABLED` (`true` enables async task dispatch)
- `APP_CELERY_BROKER_URL`
- `APP_CELERY_RESULT_BACKEND`
- `APP_LLM_MODE` (`mock`/`ollama`/`deepseek`/`openai_compatible`)
- `APP_LLM_MODEL_NAME`
- `APP_DEEPSEEK_MODEL_NAME`
- `APP_LOCAL_MODEL_ENDPOINT`
- `APP_ENTERPRISE_MODEL_ENDPOINT`
- `APP_DEEPSEEK_ENDPOINT`
- `APP_LLM_TIMEOUT_SECONDS`
- `APP_LLM_RUNTIME_CONFIG_PATH` (runtime override file path)
- `APP_SHADOW_IMPROVEMENT_THRESHOLD` (default: `0.08`)
- `APP_CANARY_SLICE_RATIO` (default: `0.05`)
- `APP_CANARY_MIN_FEEDBACK_COUNT` (default: `3`)
- `APP_AUTO_ROLLBACK_QUALITY_DROP` (default: `0.03`)
- `APP_AUTO_ROLLBACK_ERROR_RISE` (default: `0.02`)

## New Evolution Endpoints

- `POST /skills/{id}/candidate/{candidate_id}/shadow-replay`
- `GET /skills/{id}/candidate/{candidate_id}/canary-status`
- `POST /evolution/auto-promote`
- `GET /evolution/candidate-audits`
- `GET /evolution/hardening-report`
- `GET /llm/config`
- `PUT /llm/config`
- `GET /llm/token-stats`

## Security & Evolution Notes

- Candidate score fields in `POST /skills/{id}/candidate` are accepted for compatibility but ignored by the server.
- Shadow score is owned by server-side estimation / shadow replay, not client-provided values.
- Canary metrics deduplicate repeated feedback from the same `taskId` for the same candidate.
- Rollback now restores the previous skill version/config snapshot (not only metadata tags).
- If `APP_CONTROL_PLANE_API_KEY` is configured, both write endpoints and hardening/audit endpoints require that key.

## Drill & Health Scripts

- `python scripts/hardening_check.py`
: one-click hardening report (same core logic as `/evolution/hardening-report`).
- `python scripts/rollback_drill.py --skill-id plan_graph_builder`
: run a rollback drill, auto-promote candidate, then verify version/config restoration.

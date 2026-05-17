# 后端快速说明（中文）

## 1) 安装依赖

```bash
python -m pip install -e ".[dev]"
```

## 2) 启动 API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 3) 启动 Worker（可选，用于异步任务）

```bash
celery -A worker.celery_app.celery_app worker --loglevel=INFO
```

## 4) 运行测试

```bash
pytest tests -q
```

## 常用环境变量

- `APP_DATABASE_URL`（默认：`sqlite:///./beeagi.db`）
- `APP_REDIS_URL`
- `APP_CONTROL_PLANE_API_KEY`（可选，开启后写接口需要 API Key）
- `APP_CONTROL_PLANE_API_KEY_HEADER`（默认：`X-API-Key`）
- `APP_CORS_ALLOW_ORIGINS`（JSON 数组，默认含 Tauri/Vite 本地来源）
- `APP_CORS_ALLOW_METHODS`（JSON 数组，默认含 `OPTIONS`）
- `APP_CORS_ALLOW_HEADERS`（JSON 数组）
- `APP_CORS_ALLOW_CREDENTIALS`（`true/false`）
- `APP_CELERY_ENABLED`（`true` 时启用异步任务分发）
- `APP_CELERY_BROKER_URL`
- `APP_CELERY_RESULT_BACKEND`

## LLM 相关

- `APP_LLM_MODE=mock|ollama|deepseek|openai_compatible`
- `APP_LLM_MODEL_NAME`（例如：`qwen2.5:7b`）
- `APP_LLM_TIMEOUT_SECONDS`（默认：`20`）
- `APP_LOCAL_MODEL_ENDPOINT`（默认：`http://127.0.0.1:11434`）
- `APP_ENTERPRISE_MODEL_ENDPOINT`
- `APP_LLM_API_KEY`
- `APP_DEEPSEEK_ENDPOINT`（默认：`https://api.deepseek.com`）
- `APP_DEEPSEEK_MODEL_NAME`（默认：`deepseek-v4-flash`）
- `APP_DEEPSEEK_API_KEY`
- `APP_LLM_RUNTIME_CONFIG_PATH`（运行时模型配置文件，默认：`./artifacts/llm_runtime_config.json`）

## 进化与灰度策略

- `APP_SHADOW_IMPROVEMENT_THRESHOLD`（默认：`0.08`）
- `APP_CANARY_SLICE_RATIO`（默认：`0.05`）
- `APP_CANARY_MIN_FEEDBACK_COUNT`（默认：`3`）
- `APP_AUTO_ROLLBACK_QUALITY_DROP`（默认：`0.03`）
- `APP_AUTO_ROLLBACK_ERROR_RISE`（默认：`0.02`）

## 关键新增接口

- `POST /skills/{id}/candidate/{candidate_id}/shadow-replay`
- `GET /skills/{id}/candidate/{candidate_id}/canary-status`
- `POST /evolution/auto-promote`
- `GET /evolution/candidate-audits`
- `GET /evolution/hardening-report`
- `GET /llm/config`
- `PUT /llm/config`
- `GET /llm/token-stats`

## 安全与加固要点

- `POST /skills/{id}/candidate` 接口虽然兼容旧字段，但候选分数由服务端计算，客户端分数不会生效。
- 灰度统计对同一 `taskId + candidateId` 去重，防止重复反馈抬分。
- 回滚会恢复技能版本与配置快照，而不是只写一条回滚标记。
- 候选状态变更会写入独立审计表，便于追踪“谁在何时为何改变状态”。
- 当配置了 `APP_CONTROL_PLANE_API_KEY` 后，写接口以及体检/审计接口都会要求携带该 Key。

## 演练与体检脚本

- `python scripts/hardening_check.py`
: 生成一键体检报告（与 `/evolution/hardening-report` 同逻辑）。
- `python scripts/rollback_drill.py --skill-id plan_graph_builder`
: 运行回滚演练，自动执行候选晋升并验证版本/配置恢复。

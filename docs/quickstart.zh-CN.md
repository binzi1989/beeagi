# BeeAGI 快速上手（中文）

## 一、启动系统

1. 启动基础服务（可选 `docker-compose`）：
   - PostgreSQL
   - Redis
   - MinIO
2. 启动后端 API（目录：`backend/`）：
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
3. 启动桌面端（目录：`desktop/`）：
   - `npm install`
   - `npm run tauri dev`

## 二、完成一次“任务 -> 进化”闭环

1. 在 GUI 的 **Task Command Console** 发起任务。
2. 在 **Feedback Center** 提交评分与纠错。
3. 在 **Evolution Audit** 观察 `worm.proposed` 与后续事件。
4. 在 **Skills Lab** 发起候选晋升或回滚。

## 三、启用影子回放评估

1. 创建候选：`POST /skills/{id}/candidate`
2. 对候选做影子评估：`POST /skills/{id}/candidate/{candidate_id}/shadow-replay`
3. 查看 `shadowScore` 与提升比例（`improvementRatio`）。

## 四、启用真实 5% 灰度

1. 先执行一次晋升请求，让候选进入 `validated`（灰度状态）。
2. 系统会按稳定哈希自动做 5% 用户分流并记录 `canary.assigned` 事件。
3. 用户反馈会持续更新 canary 统计与 `canaryScore`（`canary.observed` 事件）。
4. 达到最小反馈样本后，再次晋升触发蜂王决策：
   - 通过：`promoted`
   - 不通过：`rolled_back`
5. 可选：调用 `POST /evolution/auto-promote` 批量自动推进候选状态。

## 五、切换真实大模型

- 本地模型（Ollama）：
  - `APP_LLM_MODE=ollama`
  - `APP_LOCAL_MODEL_ENDPOINT=http://127.0.0.1:11434`
  - `APP_LLM_MODEL_NAME=qwen2.5:7b`

- 企业网关（OpenAI 兼容）：
  - `APP_LLM_MODE=openai_compatible`
  - `APP_ENTERPRISE_MODEL_ENDPOINT=https://your-gateway`
  - `APP_LLM_API_KEY=your-token`
  - `APP_LLM_MODEL_NAME=your-model`

- DeepSeek 官方接口：
  - `APP_LLM_MODE=deepseek`
  - `APP_DEEPSEEK_ENDPOINT=https://api.deepseek.com`
  - `APP_DEEPSEEK_MODEL_NAME=deepseek-v4-flash`
  - `APP_DEEPSEEK_API_KEY=your-deepseek-key`

重启后端后，任务结果可在 `resultPayload.llmSummary` 查看模型摘要输出。

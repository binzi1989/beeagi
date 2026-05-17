# BeeAGI 快速上手（中文）

## 一、启动系统

1. 启动基础服务（可选，`docker-compose`）：
   - PostgreSQL
   - Redis
   - MinIO
2. 启动后端（目录：`backend/`）：
   - `python -m pip install -e ".[dev]"`
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
3. 启动桌面端（目录：`desktop/`）：
   - `npm install`
   - `npm run tauri dev`（或 `npm run dev`）

## 二、先完成一次最小闭环（3 步）

1. 在 `工作台` 选择场景并输入任务。  
2. 点击“执行本轮任务”或“一键跑完整流程”。  
3. 在“交付产物”区点击“**一键采纳**”或“**需要修订**”，完成反馈闭环。  

## 三、理解当前界面

- `工作台`
  - 左侧：任务输入、对话式时间线、交付产物
  - 右侧：标签页（反馈 / 进化 / 系统）
- `LLM 与 Token`
  - 模型配置（模式、模型名、端点、超时、密钥）
  - Token 统计（总量、按模型、最近任务）

## 四、进化控制最短路径

1. 创建候选：`POST /skills/{id}/candidate`  
2. 影子评估：`POST /skills/{id}/candidate/{candidate_id}/shadow-replay`  
3. 查看灰度：`GET /skills/{id}/candidate/{candidate_id}/canary-status`  
4. 晋升候选：`POST /skills/{id}/promote`  
5. 风险回滚：`POST /skills/{id}/rollback`  

可选自动推进：`POST /evolution/auto-promote`

## 五、切换真实大模型

### 方式 A：通过 LLM 页面（推荐）

进入 `LLM 与 Token` 页面，直接修改：
- 模型模式：`mock / ollama / deepseek / openai_compatible`
- 模型名称与端点
- 超时与密钥

### 方式 B：通过环境变量

- 本地模型（Ollama）：
  - `APP_LLM_MODE=ollama`
  - `APP_LOCAL_MODEL_ENDPOINT=http://127.0.0.1:11434`
  - `APP_LLM_MODEL_NAME=qwen2.5:7b`
- 企业网关（OpenAI 兼容）：
  - `APP_LLM_MODE=openai_compatible`
  - `APP_ENTERPRISE_MODEL_ENDPOINT=https://your-gateway`
  - `APP_LLM_API_KEY=your-token`
  - `APP_LLM_MODEL_NAME=your-model`
- DeepSeek：
  - `APP_LLM_MODE=deepseek`
  - `APP_DEEPSEEK_ENDPOINT=https://api.deepseek.com`
  - `APP_DEEPSEEK_MODEL_NAME=deepseek-v4-flash`
  - `APP_DEEPSEEK_API_KEY=your-deepseek-key`

生效后可在 `resultPayload.llmSummary` 查看模型输出，在 `/llm/token-stats` 查看用量统计。

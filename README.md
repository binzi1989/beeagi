# 🐝 BeeAGI: Enterprise-Grade AI Agent Swarm Platform

[![CI](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml/badge.svg)](https://github.com/binzi1989/beeagi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![TypeScript](https://img.shields.io/badge/TypeScript-Latest-blue?logo=typescript)
![Platform](https://img.shields.io/badge/Platform-Linux%20|%20macOS%20|%20Windows-brightgreen)

> **Private-first swarm orchestration for real delivery work**  
> Task planning → execution → feedback → controlled self-evolution, with full auditability.

[English](#english-version) | [中文](#中文版本)

---

## English Version

### 🎯 Why BeeAGI?

BeeAGI is **not just another AI agent framework**. It combines three critical dimensions:

| Dimension | What You Get |
|-----------|-------------|
| **Architecture** | Four-role swarm (Scout/Worker/Worm/Queen) — proven role-based task orchestration |
| **Execution** | Codex-style plan-first + tool boundaries — controllable, auditable AI workflows |
| **Evolution** | Human-in-the-loop skill upgrades with shadow replay, canary rollout, and rollback safety |

**Ideal for:**
- Autonomous task execution (coding, research, data analysis, content generation)
- Teams needing AI transparency and control
- Production systems requiring audit trails and safety governance

### ⚡ Quick Start (30 seconds)

```bash
# 1. Start backend
cd backend
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. Start frontend (in another terminal)
cd desktop
npm install
npm run dev

# 3. Open http://localhost:5173 → Choose "Coding" scenario → Run Full Workflow
```

**Expected flow:**
- Scout discovers task → Worker executes → Output delivered
- Submit feedback → Worm proposes improvements → Queen approves → New version deployed

### 🎁 What's New: Physical Deliverables

Instead of just summaries, BeeAGI **writes real files to disk**:

| Scenario | Output |
|----------|--------|
| **Coding** | Runnable project scaffold (code + tests + README) |
| **Office** | Polished documents (Word, Markdown, JSON) |
| **Research** | Analysis reports with raw data files (CSV, SQL) |
| **Debug** | Root-cause analysis with logs and fixes |
| **Data** | Processed datasets + transformation pipeline |
| **Product** | Design specs + competitive analysis |

**Setup in UI:**
1. Advanced Settings → Bind Local Delivery Folder (e.g., `D:\Bee2\deliverables`)
2. Keep "Allow Writing Artifacts" enabled
3. Run task → Check Deliverable panel for file paths

Or programmatically:
```json
{
  "constraints": {
    "workspaceBinding": {
      "targetDir": "/path/to/deliverables",
      "allowWrite": true,
      "allowExecute": false
    }
  }
}
```

### 🚀 Core Features (v0.2.0)

- ✅ **Scenario-driven workflows** — Coding, Office, Research, Debug, Data, Product
- ✅ **Chat timeline UI** — Real-time task progress and feedback loop
- ✅ **LLM flexibility** — OpenAI, Ollama, DeepSeek, local endpoints
- ✅ **Token analytics** — Per-model cost tracking and optimization
- ✅ **Autonomous life engine** — Always-on self-iteration and idle cruise mode
- ✅ **Shadow replay evaluator** — Safe candidate testing before production
- ✅ **5% canary allocator** — Real traffic validation for new skill versions
- ✅ **Auto-rollback governance** — Instant recovery if quality drops
- ✅ **Pheromone loop** — Scout-based task prioritization inspired by ant behavior

### 📊 Architecture at a Glance

```
┌─────────────────────────────────────────────────────┐
│                  Desktop UI (Tauri + React)         │
├─────────────────────────────────────────────────────┤
│                                                      │
│   [Scenario Selector]  [Chat Timeline]  [Output]   │
│                                                      │
└────────────────┬────────────────────────────────────┘
                 │ REST API
┌────────────────▼────────────────────────────────────┐
│        FastAPI Control Plane (backend)              │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │  Scout   │ │ Worker   │ │   Worm   │           │
│  │(Planning)│ │(Exec)    │ │(Evolution)           │
│  └──────────┘ └──────────┘ └──────────┘           │
│                                                      │
│  Skills Store │ Task Queue │ Evolution Engine       │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 🔌 API Reference

**Tasks:**
- `POST /tasks` — Create new task
- `GET /tasks/{id}` — Fetch task status
- `POST /tasks/{id}/feedback` — Submit manual feedback
- `POST /tasks/{id}/auto-feedback` — Automatic feedback inference

**Skills & Evolution:**
- `GET /skills` — List all skills
- `POST /skills/{id}/candidate` — Propose new skill version
- `POST /skills/{id}/promote` — Promote candidate to production
- `POST /skills/{id}/rollback` — Rollback to previous version
- `POST /skills/{id}/candidate/{candidate_id}/shadow-replay` — Test safely
- `GET /skills/{id}/candidate/{candidate_id}/canary-status` — Check rollout health

**Evolution Insights:**
- `GET /evolution/telemetry` — Progress scores, velocity, throughput
- `GET /evolution/hardening-report` — Safety audit trail
- `GET /evolution/pheromones` — Current task discovery signals

**LLM & Billing:**
- `GET /llm/config` — Current LLM routing
- `PUT /llm/config` — Update model endpoints
- `GET /llm/token-stats` — Token usage by model and task

[Full API docs →](./docs/api.md)

### 📁 Repository Structure

```
beeagi/
├── backend/                    # FastAPI control plane
│   ├── app/
│   │   ├── main.py            # API routes
│   │   ├── models/            # Data schemas
│   │   ├── services/          # Business logic
│   │   └── db/                # Database layer
│   ├── tests/                 # Unit + integration tests
│   └── scripts/               # Hardening, rollback drills
├── desktop/                   # Tauri + React UI
│   ├── src/
│   │   ├── components/        # React components
│   │   ├── pages/             # Page layouts
│   │   └── services/          # API clients
│   └── src-tauri/             # Tauri config
├── docs/                      # Architecture, tutorials, releases
│   ├── architecture/
│   ├── demo/
│   ├── releases/
│   └── growth/
└── README.md, LICENSE, etc.
```

### 🛡️ Security & Governance

- **No cloud lock-in** — Self-hosted, fully private
- **API key protection** — Control-plane auth via `APP_CONTROL_PLANE_API_KEY`
- **Audit trails** — All skill changes logged with timestamps and reasons
- **Safe rollouts** — Shadow replay + canary + rollback = zero-downtime updates
- **CORS configurable** — Restrict frontend origins as needed

### 🌍 Multi-language Support

- English: [README.md](./README.md)
- 中文: [README.zh-CN.md](./README.zh-CN.md)

### 📚 Documentation

- [30-second demo script](./docs/demo/30s-demo-script.md)
- [Architecture deep dive](./docs/architecture/)
- [Release notes (v0.2.0)](./docs/releases/v0.2.0.md)
- [Contributing guide](./CONTRIBUTING.md)
- [GitHub launch playbook (Chinese)](./docs/growth/github-launch-playbook.zh-CN.md)

### 💻 System Requirements

| Component | Requirement |
|-----------|------------|
| Python | 3.9+ |
| Node.js | 16+ |
| RAM | 2GB minimum (4GB+ recommended) |
| Disk | 500MB (+ LLM model size if local) |
| DB | SQLite (default) or PostgreSQL |

### 🔧 Environment Setup

**Backend:**
```bash
APP_LLM_MODE=deepseek              # or ollama, openai_compatible, mock
APP_DEEPSEEK_API_KEY=sk_...
APP_LOCAL_MODEL_ENDPOINT=http://localhost:11434
APP_CONTROL_PLANE_API_KEY=your-secure-key
APP_DATABASE_URL=sqlite:///./beeagi.db
```

**Frontend:**
```bash
VITE_API_BASE_URL=http://localhost:8000
VITE_CONTROL_PLANE_API_KEY=your-secure-key
```

[Full env reference →](./backend/README.md#environment-variables)

### 📈 Benchmarks (Preliminary)

- **Scout planning latency:** < 2s (cached context)
- **Worker execution:** Depends on LLM (Ollama: 10-30s, DeepSeek: 5-15s)
- **Feedback processing:** < 1s
- **Skill evolution cycle:** 5-10 min (shadow replay) + rollout monitoring

### 🤝 Contributing

We welcome PRs, bug reports, and feature ideas!

- [CONTRIBUTING.md](./CONTRIBUTING.md) — How to contribute
- [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) — Community guidelines
- [SECURITY.md](./SECURITY.md) — Responsible disclosure
- [Issue templates](./.github/ISSUE_TEMPLATE) — Bug reports, features

### 📝 License

MIT License — Use freely in commercial and personal projects.

### 🎯 Roadmap

**v0.3.0 (Coming Soon):**
- Multi-agent collaboration (swarm sync)
- GraphQL API support
- Native observability (Prometheus, Jaeger)
- Advanced pheromone tuning

**v0.4.0 (Future):**
- Kubernetes operator
- Fine-tuning pipeline integration
- Web-based skill marketplace

### 💬 Questions?

- **Issues:** [GitHub Issues](https://github.com/binzi1989/beeagi/issues)
- **Discussions:** [GitHub Discussions](https://github.com/binzi1989/beeagi/discussions)
- **Email:** binzi1989@gmail.com

---

## 中文版本

中文文档请查看 [README.zh-CN.md](./README.zh-CN.md)

**快速启动：**
```bash
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload
# 另开终端
cd desktop && npm install && npm run dev
```

更多信息：
- [项目价值与架构](./README.zh-CN.md#项目价值)
- [30秒启动指南](./README.zh-CN.md#30-秒启动)
- [实物交付功能](./README.zh-CN.md#实物交付重点)
- [生长手册](./docs/growth/github-launch-playbook.zh-CN.md)

---

**Made with ❤️ by the BeeAGI team**

# Changelog

All notable changes to this project are documented here.

## v0.2.0 - 2026-05-17

### Added

- Active Scout pheromone loop (deposit, evaporation, task injection, reward, patrol)
- Evolution APIs: `GET /evolution/pheromones`, `POST /evolution/scout-patrol`
- Desktop pheromone panel with one-click patrol action
- New backend tests for Scout pheromone closed-loop behavior
- Demo assets and launch docs:
  - `docs/demo/30s-demo-script.md`
  - `docs/demo/30s-demo-script.zh-CN.md`
  - `docs/growth/github-launch-playbook.zh-CN.md`
  - `docs/releases/v0.2.0.md`
  - `docs/releases/v0.2.0.zh-CN.md`

### Changed

- Reworked `README.md` and `README.zh-CN.md` for clearer onboarding and open-source distribution

## v0.1.0 - 2026-05-17

### Added

- Four-role swarm execution loop: Scout, Worker, Worm, Queen
- Task lifecycle APIs, feedback APIs, evolution APIs
- Shadow replay evaluator and 5% canary allocator
- Candidate promotion/rollback and audit trail
- LLM routing modes: mock, ollama, deepseek, openai_compatible
- LLM runtime config APIs and token statistics APIs
- Desktop scenario workspace with chat-style timeline
- Deliverable-first UI and quick accept/refine feedback actions
- Dedicated LLM Console page for model settings and token metrics
- CI workflow, contribution docs, code of conduct, security policy

### Changed

- Frontend optimized to reduce operator cognitive load with tabbed right rail
- Feedback loop strengthened with auto-inferred feedback path

### Security

- Write endpoints support control-plane API key guard
- Runtime and artifact files excluded via `.gitignore`

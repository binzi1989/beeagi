# BeeAGI Architecture (V1)

## Runtime Topology

- Desktop GUI (Tauri + React)
- FastAPI control plane (task API, skill API, evolution API)
- Celery worker (async task execution)
- PostgreSQL (state + audit)
- Redis Streams (event bus)
- MinIO (artifacts and replay bundles)

## Core Lifecycle

1. `POST /tasks` receives `TaskSpec`.
2. Scout generates reconnaissance packet and publishes `scout.reported`.
3. Worker creates `PlanGraph`, publishes `worker.planned`.
4. Worker executes selected skills and publishes `worker.completed`.
5. Feedback is ingested through `POST /tasks/{id}/feedback`, publishing `feedback.received`.
6. Worm proposes `SkillDelta` candidate and publishes `worm.proposed`.
7. Shadow replay can be invoked through candidate endpoint, publishing `shadow.evaluated`.
8. Validated candidates enter deterministic 5% canary routing, publishing `canary.assigned`.
9. Canary feedback updates candidate score and publishes `canary.observed`.
10. Queen evaluates thresholds and promotes or rolls back via events.

## Controlled Evolution Defaults

- Shadow replay improvement threshold: >= 8%
- Canary slice: 5%
- Auto rollback when quality drops > 3%
- Auto rollback when error rate rises > 2%

# 30-Second Demo Script (EN)

## Goal

Show that BeeAGI can go from task input to deliverable, then use feedback to trigger evolution.

## Before Demo

- Backend running at `http://127.0.0.1:8000`
- Desktop app running
- Open workspace page (not LLM console page)

## Live Script

### 0-10s: Task setup

1. Select scenario: `Coding`.
2. Goal:
   - `Implement user status filter + pagination and add tests`
3. Context refs:
   - `repo://frontend/src/pages/users,repo://backend/app/api/routes/users.py`
4. Constraints JSON:

```json
{
  "doneWhen": ["tests pass", "lint clean", "api backward compatible"],
  "language": "en"
}
```

### 10-20s: Run workflow

1. Click `Run Full Workflow`.
2. Narrate:
   - "Scout scans context"
   - "Worker plans and executes"
   - "Deliverable appears in main panel"

### 20-30s: Feedback + evolution

1. Click `Run Auto Feedback Now` (or submit manual feedback).
2. Open right rail -> `Evolution`.
3. Show:
   - Swarm event updates
   - Scout pheromone cards
   - Optional `Run Patrol`

## Closing Line

"BeeAGI doesn't just finish tasks. It learns from real user feedback, verifies changes safely, and evolves under governance."

# Desktop GUI Quick Start

## 1) Install dependencies

```bash
npm install
```

## 2) Start web UI

```bash
npm run dev
```

## 3) Start Tauri desktop shell

```bash
npm run tauri dev
```

## Optional environment variable

- `VITE_API_BASE_URL` (default: `http://127.0.0.1:8000`)
- `VITE_CONTROL_PLANE_API_KEY` (required if backend write endpoints are API-key protected)

## Scenario-first UI

- The desktop UI is now scenario-first, not feature-first.
- Built-in scenario templates:
  - Coding (`Implement -> Review -> Fix`)
  - Office (`Organize -> Generate -> Revise`)
  - Research (`Retrieve -> Analyze -> Conclude`)
  - Plus extra scenarios: Debug, Data Workflow, Product Design, Growth Ops
- You can run a full scenario workflow in one click (`Run Full Workflow`), and still run single tasks manually.

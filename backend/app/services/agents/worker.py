from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.task import Task
from app.schemas.tasks import TaskSpec
from app.services.model_router import ModelRouter


class WorkerAgent:
    def __init__(self, model_router: ModelRouter | None = None) -> None:
        self.model_router = model_router

    def _safe_int(self, value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    def _resolve_swarm_counts(self, constraints: dict[str, Any]) -> tuple[int, int]:
        swarm = constraints.get("swarmConfig") if isinstance(constraints, dict) else {}
        if not isinstance(swarm, dict):
            swarm = {}
        worker_count = self._safe_int(swarm.get("workerCount"), default=3, minimum=1, maximum=12)
        scout_count = self._safe_int(swarm.get("scoutCount"), default=2, minimum=1, maximum=12)
        return worker_count, scout_count

    def _collect_patch_effects(self, selected_skills: list[dict[str, Any]]) -> dict[str, Any]:
        patch_effects = {
            "promptTweaks": {},
            "toolPolicy": {},
            "sourceCandidates": [],
        }
        for runtime in selected_skills:
            if runtime.get("variant") != "canary":
                continue
            patch = runtime.get("candidatePatch")
            if not isinstance(patch, dict):
                continue
            prompt_tweaks = patch.get("promptTweaks")
            if isinstance(prompt_tweaks, dict):
                patch_effects["promptTweaks"].update(prompt_tweaks)
            tool_policy = patch.get("toolPolicy")
            if isinstance(tool_policy, dict):
                patch_effects["toolPolicy"].update(tool_policy)
            candidate_id = runtime.get("candidateId")
            if candidate_id:
                patch_effects["sourceCandidates"].append(candidate_id)
        return patch_effects

    def build_plan(self, spec: TaskSpec, scout_report: dict[str, Any]) -> dict[str, Any]:
        worker_count, scout_count = self._resolve_swarm_counts(spec.constraints)
        nodes = [{"id": "n1", "title": "Analyze intent", "owner": "worker-1"}]
        edges: list[dict[str, str]] = []

        previous = "n1"
        worker_node_ids: list[str] = []
        for idx in range(worker_count):
            node_id = f"w{idx + 1}"
            worker_node_ids.append(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "title": f"Worker {idx + 1} parallel draft",
                    "owner": f"worker-{idx + 1}",
                }
            )
            edges.append({"from": previous, "to": node_id})

        ensemble_node = "ens1"
        nodes.append({"id": ensemble_node, "title": "Ensemble vote & recommendation", "owner": "worker-ensemble"})
        for worker_node in worker_node_ids:
            edges.append({"from": worker_node, "to": ensemble_node})

        execute_node = "n_exec"
        synth_node = "n_synth"
        nodes.extend(
            [
                {"id": execute_node, "title": "Execute toolchain", "owner": "worker-runtime"},
                {"id": synth_node, "title": "Synthesize output", "owner": "worker-runtime"},
            ]
        )
        edges.extend(
            [
                {"from": ensemble_node, "to": execute_node},
                {"from": execute_node, "to": synth_node},
            ]
        )

        risk_flags = list(scout_report.get("riskFlags", []))
        if worker_count >= 8:
            risk_flags.append("high_worker_parallelism_cost")
        return {
            "nodes": nodes,
            "edges": edges,
            "riskFlags": risk_flags,
            "swarmConfig": {"workerCount": worker_count, "scoutCount": scout_count},
        }

    def execute(
        self,
        task: Task,
        selected_skills: list[dict[str, Any]],
        scout_pheromones: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = datetime.now(timezone.utc)
        constraints = task.constraints if isinstance(task.constraints, dict) else {}
        worker_count, scout_count = self._resolve_swarm_counts(constraints)
        patch_effects = self._collect_patch_effects(selected_skills)
        prompt_tweaks = patch_effects.get("promptTweaks", {})
        tool_policy = patch_effects.get("toolPolicy", {})
        scout_pheromones = scout_pheromones or []

        max_retries = tool_policy.get("maxRetries") if isinstance(tool_policy, dict) else None
        prefer_low_risk = bool(tool_policy.get("preferLowRiskTools")) if isinstance(tool_policy, dict) else False
        format_hint = prompt_tweaks.get("format") if isinstance(prompt_tweaks, dict) else None
        style_hint = prompt_tweaks.get("style") if isinstance(prompt_tweaks, dict) else None

        prompt_suffix = ""
        if format_hint:
            prompt_suffix += f"\nOutput format hint: {format_hint}"
        if style_hint:
            prompt_suffix += f"\nStyle hint: {style_hint}"
        if isinstance(max_retries, int):
            prompt_suffix += f"\nTool retry budget override: {max_retries}"
        if prefer_low_risk:
            prompt_suffix += "\nPrefer low-risk tool paths when tradeoffs are close."

        prompt = (
            f"Task goal: {task.goal}\n"
            f"Constraints: {task.constraints}\n"
            f"Quality target: {task.quality_target}\n"
            f"Selected skills: {selected_skills}\n"
            f"Scout pheromones: {scout_pheromones}\n"
            "Generate a concise execution summary and key risks."
            f"{prompt_suffix}"
        )
        llm_output = None
        llm_meta: dict[str, Any] | None = None
        if self.model_router is not None:
            try:
                llm_result = self.model_router.generate(prompt)
                llm_output = llm_result.text
                llm_meta = {
                    "provider": llm_result.provider,
                    "model": llm_result.model,
                }
            except Exception as exc:  # pragma: no cover
                llm_output = f"LLM call failed: {exc}"
                llm_meta = {"provider": "error", "model": "n/a"}

        quality_estimate = min(0.98, max(0.6, task.quality_target - 0.02))
        if format_hint:
            quality_estimate = min(0.98, quality_estimate + 0.02)
        if prefer_low_risk:
            quality_estimate = min(0.98, quality_estimate + 0.01)

        result = {
            "summary": (
                f"Task '{task.goal}' executed with {len(selected_skills)} skills, "
                f"{worker_count} workers and {scout_count} scouts."
            ),
            "selectedSkills": selected_skills,
            "qualityEstimate": quality_estimate,
            "llmSummary": llm_output,
            "llmMeta": llm_meta,
            "swarmTelemetry": {
                "workerCount": worker_count,
                "scoutCount": scout_count,
                "ensembleMode": "weighted-vote",
                "ensembleRecommendation": "blend top 2 worker drafts then execute risk-aware path",
            },
            "appliedPatchSummary": {
                "promptTweaks": prompt_tweaks,
                "toolPolicy": tool_policy,
                "sourceCandidates": patch_effects["sourceCandidates"],
            },
            "scoutPheromones": scout_pheromones,
        }
        completed = datetime.now(timezone.utc)
        retry_count = 0
        if isinstance(max_retries, int):
            retry_count = max(0, min(max_retries, 5))

        error_rate = 0.0
        if prefer_low_risk:
            error_rate = 0.0
        elif isinstance(max_retries, int) and max_retries <= 1:
            error_rate = 0.01

        prompt_tokens = max(24, len(prompt) // 4)
        completion_source = llm_output or result["summary"]
        completion_tokens = max(24, len(str(completion_source)) // 4)
        total_tokens = prompt_tokens + completion_tokens

        metrics = {
            "durationMs": int((completed - started).total_seconds() * 1000) + 120,
            "retryCount": retry_count,
            "tokenEstimate": total_tokens,
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "totalTokens": total_tokens,
            "errorRate": error_rate,
            "workerCount": worker_count,
            "scoutCount": scout_count,
        }
        return result, metrics

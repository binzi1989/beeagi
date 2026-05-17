from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.task import Task
from app.schemas.tasks import TaskSpec
from app.services.model_router import ModelRouter


class WorkerAgent:
    def __init__(self, model_router: ModelRouter | None = None) -> None:
        self.model_router = model_router

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
        nodes = [
            {"id": "n1", "title": "Analyze intent", "owner": "worker"},
            {"id": "n2", "title": "Select skills", "owner": "worker"},
            {"id": "n3", "title": "Execute toolchain", "owner": "worker"},
            {"id": "n4", "title": "Synthesize output", "owner": "worker"},
        ]
        edges = [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
            {"from": "n3", "to": "n4"},
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "riskFlags": scout_report.get("riskFlags", []),
        }

    def execute(
        self,
        task: Task,
        selected_skills: list[dict[str, Any]],
        scout_pheromones: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = datetime.now(timezone.utc)
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
            "summary": f"Task '{task.goal}' executed with {len(selected_skills)} skills.",
            "selectedSkills": selected_skills,
            "qualityEstimate": quality_estimate,
            "llmSummary": llm_output,
            "llmMeta": llm_meta,
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
        }
        return result, metrics

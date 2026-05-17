from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.feedback import TaskFeedback
from app.models.task import Task


def _clamp_score(score: float) -> float:
    return max(0.0, min(1.0, score))


@dataclass(slots=True)
class ReplayScores:
    baseline_score: float
    candidate_score: float


class ShadowReplayEvaluator:
    def estimate(
        self,
        *,
        patch: dict[str, Any],
        tasks: list[Task],
        feedback_by_task: dict[str, TaskFeedback],
    ) -> dict[str, Any]:
        sample_size = len(tasks)
        if sample_size == 0:
            return {
                "sampleSize": 0,
                "baselineAverage": 0.0,
                "candidateAverage": 0.0,
                "improvementRatio": 1.0,
                "shadowScore": 1.0,
                "notes": "no historical tasks available",
                "taskBreakdown": [],
            }

        breakdown: list[dict[str, Any]] = []
        baseline_total = 0.0
        candidate_total = 0.0
        for task in tasks:
            feedback = feedback_by_task.get(task.id)
            scores = self._score_one(task=task, feedback=feedback, patch=patch)
            baseline_total += scores.baseline_score
            candidate_total += scores.candidate_score
            breakdown.append(
                {
                    "taskId": task.id,
                    "baseline": round(scores.baseline_score, 4),
                    "candidate": round(scores.candidate_score, 4),
                }
            )

        baseline_avg = baseline_total / sample_size
        candidate_avg = candidate_total / sample_size
        improvement_ratio = 1.0 if baseline_avg <= 0 else candidate_avg / baseline_avg
        return {
            "sampleSize": sample_size,
            "baselineAverage": round(baseline_avg, 4),
            "candidateAverage": round(candidate_avg, 4),
            "improvementRatio": round(improvement_ratio, 4),
            "shadowScore": round(improvement_ratio, 4),
            "notes": "shadow replay uses historical quality/feedback with patch heuristics",
            "taskBreakdown": breakdown[:20],
        }

    def _score_one(self, *, task: Task, feedback: TaskFeedback | None, patch: dict[str, Any]) -> ReplayScores:
        result_payload = task.result_payload or {}
        metrics = task.metrics or {}

        if feedback and feedback.explicit_score is not None:
            baseline = float(feedback.explicit_score)
        else:
            baseline = float(result_payload.get("qualityEstimate", task.quality_target))

        retry_penalty = min(0.08, float(metrics.get("retryCount", 0)) * 0.015)
        error_penalty = min(0.1, float(metrics.get("errorRate", 0.0)) * 0.2)
        baseline = _clamp_score(baseline - retry_penalty - error_penalty)

        uplift = 0.0
        if "promptTweaks" in patch:
            uplift += 0.05
        if "toolPolicy" in patch:
            uplift += 0.04

        max_retries = (patch.get("toolPolicy") or {}).get("maxRetries")
        if isinstance(max_retries, int) and max_retries <= 1:
            uplift -= 0.01

        risk_flags = (task.plan_graph or {}).get("riskFlags", [])
        if isinstance(risk_flags, list) and len(risk_flags) > 0:
            uplift += 0.02

        candidate = _clamp_score(baseline + uplift)
        return ReplayScores(baseline_score=baseline, candidate_score=candidate)

from __future__ import annotations

from app.models.feedback import TaskFeedback
from app.models.skill import Skill
from app.models.task import Task


class WormAgent:
    def derive_skill_delta(self, task: Task, feedback: TaskFeedback, skill: Skill) -> dict[str, object]:
        explicit = feedback.explicit_score if feedback.explicit_score is not None else 0.75
        implicit_retry = float(feedback.implicit_signals.get("retryCount", 0))
        adoption_rate = float(feedback.implicit_signals.get("adoptionRate", 0.8))
        edit_distance = float(feedback.implicit_signals.get("editDistance", 0.1))

        shadow_gain = max(0.0, min(0.25, (explicit - 0.7) * 0.3 + adoption_rate * 0.1 - edit_distance * 0.05))
        shadow_score = 1.0 + shadow_gain
        canary_score = max(0.0, shadow_score - implicit_retry * 0.02)

        patch = {
            "promptTweaks": {
                "goalPattern": task.goal[:120],
                "reinforce": ["constraint-awareness", "structured-final-answer"],
            },
            "toolPolicy": {
                "maxRetries": 2,
                "preferLowRiskTools": True,
            },
        }
        evidence = {
            "taskId": task.id,
            "baseSkill": skill.id,
            "explicitScore": explicit,
            "implicitSignals": feedback.implicit_signals,
            "canaryErrorRise": float(feedback.implicit_signals.get("errorRateRise", 0.0)),
            "corrections": feedback.corrections,
        }
        return {
            "shadowScore": shadow_score,
            "canaryScore": canary_score,
            "changeType": "prompt_and_policy_tuning",
            "patch": patch,
            "evidence": evidence,
        }

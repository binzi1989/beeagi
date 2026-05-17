from __future__ import annotations

from app.core.config import Settings
from app.models.skill import SkillCandidate


class QueenAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def decide(self, candidate: SkillCandidate) -> tuple[str, str]:
        shadow_delta = candidate.shadow_score - 1.0
        if shadow_delta < self.settings.shadow_improvement_threshold:
            return (
                "rejected",
                f"shadow improvement {shadow_delta:.3f} is below threshold {self.settings.shadow_improvement_threshold:.3f}",
            )

        error_rise = float(candidate.evidence.get("canaryErrorRise", 0.0))
        if error_rise > self.settings.auto_rollback_error_rise:
            return (
                "rolled_back",
                f"canary error rise {error_rise:.3f} exceeded {self.settings.auto_rollback_error_rise:.3f}",
            )

        if candidate.canary_score is None:
            return ("validated", "shadow passed; waiting canary score")

        quality_drop = max(0.0, 1.0 - candidate.canary_score)
        if quality_drop > self.settings.auto_rollback_quality_drop:
            return (
                "rolled_back",
                f"canary quality drop {quality_drop:.3f} exceeded {self.settings.auto_rollback_quality_drop:.3f}",
            )

        return ("promoted", "shadow and canary checks passed")

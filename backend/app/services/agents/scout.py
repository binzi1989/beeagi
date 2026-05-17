from datetime import datetime, timezone
from typing import Any

from app.schemas.tasks import TaskSpec


class ScoutAgent:
    def scan(self, spec: TaskSpec) -> dict[str, Any]:
        risk_flags: list[str] = []
        if not spec.context_refs:
            risk_flags.append("missing_context_refs")
        if spec.quality_target >= 0.95:
            risk_flags.append("high_quality_target")

        return {
            "source": "scout-agent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contextCount": len(spec.context_refs),
            "constraintsSummary": list(spec.constraints.keys()),
            "confidence": max(0.5, min(0.98, 0.65 + len(spec.context_refs) * 0.03)),
            "riskFlags": risk_flags,
        }

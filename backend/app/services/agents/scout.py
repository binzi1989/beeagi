from datetime import datetime, timezone
import re
from typing import Any

from app.schemas.tasks import TaskSpec


class ScoutAgent:
    def _extract_source(self, route: str) -> str:
        if "://" not in route:
            return "context"
        prefix = route.split("://", 1)[0].strip().lower()
        if prefix:
            return prefix
        return "context"

    def _estimate_reliability(self, source: str) -> float:
        source_weights = {
            "repo": 0.86,
            "db": 0.82,
            "doc": 0.76,
            "api": 0.78,
            "log": 0.7,
            "trace": 0.72,
            "context": 0.68,
        }
        return source_weights.get(source, 0.66)

    def _estimate_novelty(self, route: str) -> float:
        lowered = route.lower()
        novelty = 0.5
        if any(flag in lowered for flag in ["today", "latest", "new", "incremental"]):
            novelty += 0.15
        if re.search(r"\d{4}-\d{2}-\d{2}", lowered):
            novelty += 0.08
        return max(0.25, min(0.95, novelty))

    def scan(self, spec: TaskSpec) -> dict[str, Any]:
        risk_flags: list[str] = []
        if not spec.context_refs:
            risk_flags.append("missing_context_refs")
        if spec.quality_target >= 0.95:
            risk_flags.append("high_quality_target")

        signals: list[dict[str, Any]] = []
        for route in spec.context_refs:
            source = self._extract_source(route)
            signals.append(
                {
                    "source": source,
                    "route": route,
                    "novelty": self._estimate_novelty(route),
                    "reliability": self._estimate_reliability(source),
                    "cost": 0.06 if source in {"repo", "db"} else 0.1,
                }
            )

        if spec.constraints:
            signals.append(
                {
                    "source": "constraints",
                    "route": "constraints://task-spec",
                    "novelty": 0.42,
                    "reliability": 0.82,
                    "cost": 0.03,
                    "notes": f"{len(spec.constraints)} constraints supplied",
                }
            )

        return {
            "source": "scout-agent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contextCount": len(spec.context_refs),
            "constraintsSummary": list(spec.constraints.keys()),
            "confidence": max(0.5, min(0.98, 0.65 + len(spec.context_refs) * 0.03)),
            "riskFlags": risk_flags,
            "signals": signals,
        }

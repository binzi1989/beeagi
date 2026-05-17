from datetime import datetime, timezone
import re
from typing import Any

from app.schemas.tasks import TaskSpec


class ScoutAgent:
    def _safe_int(self, value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    def _extract_mcp_connectors(self, constraints: dict[str, Any]) -> list[str]:
        raw = constraints.get("mcpConnectors")
        if not isinstance(raw, list):
            return []
        connectors: list[str] = []
        for item in raw:
            text = str(item).strip()
            if not text:
                continue
            connectors.append(text[:120])
        return connectors[:20]

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
        swarm_config = spec.constraints.get("swarmConfig") if isinstance(spec.constraints, dict) else {}
        if not isinstance(swarm_config, dict):
            swarm_config = {}
        scout_count = self._safe_int(swarm_config.get("scoutCount"), default=2, minimum=1, maximum=12)
        mcp_connectors = self._extract_mcp_connectors(spec.constraints)

        risk_flags: list[str] = []
        if not spec.context_refs:
            risk_flags.append("missing_context_refs")
        if spec.quality_target >= 0.95:
            risk_flags.append("high_quality_target")
        if scout_count >= 6:
            risk_flags.append("high_scout_fanout_cost")

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

        for connector in mcp_connectors:
            route = connector if "://" in connector else f"mcp://{connector}"
            signals.append(
                {
                    "source": "mcp",
                    "route": route,
                    "novelty": min(0.95, self._estimate_novelty(route) + 0.12),
                    "reliability": max(0.7, self._estimate_reliability("api")),
                    "cost": 0.12,
                    "notes": "mcp connector signal",
                }
            )

        if scout_count > 1:
            for idx in range(scout_count):
                novelty = max(0.3, min(0.95, 0.44 + idx * 0.03))
                reliability = max(0.55, min(0.9, 0.64 + idx * 0.02))
                signals.append(
                    {
                        "source": "scout_squad",
                        "route": f"scout://squad-{idx + 1}",
                        "novelty": novelty,
                        "reliability": reliability,
                        "cost": 0.05,
                        "notes": "parallel scout auto-sensing",
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
            "swarmConfig": {
                "scoutCount": scout_count,
                "mcpConnectors": mcp_connectors,
            },
            "constraintsSummary": list(spec.constraints.keys()),
            "confidence": max(
                0.5,
                min(
                    0.98,
                    0.65 + len(spec.context_refs) * 0.03 + len(mcp_connectors) * 0.02 + min(scout_count, 6) * 0.01,
                ),
            ),
            "riskFlags": risk_flags,
            "signals": signals,
        }

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.skill import SkillCandidate
from app.schemas.skills import SkillDelta
from app.services.event_bus import build_event_bus
from app.services.model_router import ModelRouter
from app.services.pipeline import PipelineService


def _build_pipeline() -> PipelineService:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    return PipelineService(
        session_factory=SessionLocal,
        event_bus=build_event_bus(settings.redis_url),
        settings=settings,
        model_router=ModelRouter(settings),
    )


def run_rollback_drill(skill_id: str | None, approved_by: str) -> dict[str, Any]:
    pipeline = _build_pipeline()
    skills = pipeline.list_skills()
    if not skills:
        raise RuntimeError("no skills available for rollback drill")

    selected_skill = None
    if skill_id:
        selected_skill = next((item for item in skills if item.id == skill_id), None)
        if selected_skill is None:
            raise RuntimeError(f"skill not found: {skill_id}")
    else:
        selected_skill = skills[0]

    baseline_version = selected_skill.version
    baseline_config = dict(selected_skill.config or {})

    candidate = pipeline.create_candidate(
        selected_skill.id,
        SkillDelta(
            target_skill=selected_skill.id,
            change_type="rollback_drill",
            patch={"promptTweaks": {"style": "rollback-drill"}, "toolPolicy": {"maxRetries": 2}},
            evidence={"source": "rollback_drill_script"},
        ),
    )

    first_candidate, first_decision, first_reason = pipeline.promote_candidate(
        selected_skill.id,
        candidate.id,
        approved_by=approved_by,
    )
    if first_decision not in {"validated", "promoted"}:
        raise RuntimeError(f"drill failed on first decision: {first_decision} ({first_reason})")

    if first_decision == "validated":
        with SessionLocal() as db:
            row = db.get(SkillCandidate, candidate.id)
            if row is None:
                raise RuntimeError("candidate disappeared during drill")
            row.canary_score = 0.99
            row.evidence = {
                **dict(row.evidence or {}),
                "canaryStats": {"feedbackCount": 3},
                "canaryErrorRise": 0.0,
            }
            db.commit()

        second_candidate, second_decision, second_reason = pipeline.promote_candidate(
            selected_skill.id,
            candidate.id,
            approved_by=approved_by,
        )
        if second_decision != "promoted":
            raise RuntimeError(f"drill failed on second decision: {second_decision} ({second_reason})")
        promoted_candidate = second_candidate
    else:
        promoted_candidate = first_candidate

    promoted_skill = next(item for item in pipeline.list_skills() if item.id == selected_skill.id)
    rolled_back_skill = pipeline.rollback_skill(
        selected_skill.id,
        reason="rollback_drill_script",
        requested_by=approved_by,
    )

    restored = {
        "versionRestored": rolled_back_skill.version == baseline_version,
        "strategyRestored": rolled_back_skill.config.get("strategy") == baseline_config.get("strategy"),
    }
    status = "pass" if all(restored.values()) else "warn"
    return {
        "status": status,
        "skillId": selected_skill.id,
        "candidateId": promoted_candidate.id,
        "baselineVersion": baseline_version,
        "promotedVersion": promoted_skill.version,
        "rolledBackVersion": rolled_back_skill.version,
        "restored": restored,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rollback drill for BeeAGI skills.")
    parser.add_argument("--skill-id", default=None, help="target skill id; defaults to first skill")
    parser.add_argument("--approved-by", default="queen-drill", help="approver identity for audit trail")
    args = parser.parse_args()

    result = run_rollback_drill(skill_id=args.skill_id, approved_by=args.approved_by)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

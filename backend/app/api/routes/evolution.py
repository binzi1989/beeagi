from fastapi import APIRouter, Depends, Query

from app.api.deps import get_pipeline
from app.api.security import require_control_plane_api_key
from app.schemas.evolution import (
    AutoPromoteRequest,
    AutoPromoteResponse,
    CandidateStatusAuditView,
    EvolutionEventView,
    HardeningReportResponse,
)
from app.services.pipeline import PipelineService

router = APIRouter()


@router.get("/events", response_model=list[EvolutionEventView], response_model_by_alias=True)
def get_events(
    limit: int = Query(default=100, ge=1, le=1000),
    topic: str | None = Query(default=None),
    pipeline: PipelineService = Depends(get_pipeline),
) -> list[EvolutionEventView]:
    events = pipeline.list_events(limit=limit, topic=topic)
    return [EvolutionEventView.model_validate(evt) for evt in events]


@router.get("/candidate-audits", response_model=list[CandidateStatusAuditView], response_model_by_alias=True)
def get_candidate_audits(
    limit: int = Query(default=100, ge=1, le=1000),
    candidate_id: str | None = Query(default=None, alias="candidateId"),
    skill_id: str | None = Query(default=None, alias="skillId"),
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
) -> list[CandidateStatusAuditView]:
    audits = pipeline.list_candidate_audits(
        limit=limit,
        candidate_id=candidate_id,
        skill_id=skill_id,
    )
    return [CandidateStatusAuditView.model_validate(item) for item in audits]


@router.get("/hardening-report", response_model=HardeningReportResponse, response_model_by_alias=True)
def get_hardening_report(
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
) -> HardeningReportResponse:
    report = pipeline.build_hardening_report()
    return HardeningReportResponse.model_validate(report)


@router.post("/auto-promote", response_model=AutoPromoteResponse, response_model_by_alias=True)
def auto_promote(
    payload: AutoPromoteRequest,
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
) -> AutoPromoteResponse:
    outcomes = pipeline.auto_promote_candidates(
        limit=payload.limit,
        approved_by=payload.approved_by,
    )
    decision_count = {
        "promoted": 0,
        "rolled_back": 0,
        "validated": 0,
        "rejected": 0,
        "skipped": 0,
    }
    for item in outcomes:
        decision = str(item["decision"])
        if decision in decision_count:
            decision_count[decision] += 1
        else:
            decision_count["skipped"] += 1

    return AutoPromoteResponse(
        total=len(outcomes),
        promoted=decision_count["promoted"],
        rolled_back=decision_count["rolled_back"],
        validated=decision_count["validated"],
        rejected=decision_count["rejected"],
        skipped=decision_count["skipped"],
        outcomes=outcomes,
    )

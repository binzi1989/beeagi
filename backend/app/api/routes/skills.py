from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_pipeline
from app.api.security import require_control_plane_api_key
from app.schemas.skills import (
    CanaryStatusResponse,
    CandidateResponse,
    CreateCandidateRequest,
    PromoteRequest,
    RollbackRequest,
    ShadowReplayRequest,
    ShadowReplayResponse,
    SkillCard,
)
from app.services.pipeline import PipelineService

router = APIRouter()


@router.get("", response_model=list[SkillCard], response_model_by_alias=True)
def list_skills(pipeline: PipelineService = Depends(get_pipeline)) -> list[SkillCard]:
    skills = pipeline.list_skills()
    return [SkillCard.model_validate(skill) for skill in skills]


@router.post("/{skill_id}/candidate", response_model=CandidateResponse, response_model_by_alias=True)
def create_candidate(
    skill_id: str,
    payload: CreateCandidateRequest,
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
) -> CandidateResponse:
    try:
        candidate = pipeline.create_candidate(
            skill_id=skill_id,
            delta=payload.delta,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return CandidateResponse.model_validate(candidate)


@router.post("/{skill_id}/promote", response_model=dict)
def promote_candidate(
    skill_id: str,
    payload: PromoteRequest,
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
) -> dict:
    try:
        candidate, decision, reason = pipeline.promote_candidate(
            skill_id,
            payload.candidate_id,
            payload.approved_by,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {
        "candidateId": candidate.id,
        "status": candidate.status,
        "decision": decision,
        "reason": reason,
    }


@router.post("/{skill_id}/rollback", response_model=SkillCard, response_model_by_alias=True)
def rollback_skill(
    skill_id: str,
    payload: RollbackRequest,
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
) -> SkillCard:
    try:
        skill = pipeline.rollback_skill(skill_id, reason=payload.reason, requested_by=payload.requested_by)
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return SkillCard.model_validate(skill)


@router.post(
    "/{skill_id}/candidate/{candidate_id}/shadow-replay",
    response_model=ShadowReplayResponse,
    response_model_by_alias=True,
)
def evaluate_shadow_replay(
    skill_id: str,
    candidate_id: str,
    payload: ShadowReplayRequest,
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
) -> ShadowReplayResponse:
    try:
        candidate, replay = pipeline.evaluate_shadow_replay(
            skill_id=skill_id,
            candidate_id=candidate_id,
            sample_size=payload.sample_size,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return ShadowReplayResponse(
        candidate_id=candidate.id,
        skill_id=skill_id,
        status=candidate.status,
        shadow_score=candidate.shadow_score,
        sample_size=int(replay["sampleSize"]),
        baseline_average=float(replay["baselineAverage"]),
        candidate_average=float(replay["candidateAverage"]),
        improvement_ratio=float(replay["improvementRatio"]),
    )


@router.get(
    "/{skill_id}/candidate/{candidate_id}/canary-status",
    response_model=CanaryStatusResponse,
    response_model_by_alias=True,
)
def get_canary_status(
    skill_id: str,
    candidate_id: str,
    pipeline: PipelineService = Depends(get_pipeline),
) -> CanaryStatusResponse:
    try:
        candidate = pipeline.get_candidate(skill_id=skill_id, candidate_id=candidate_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    stats = dict((candidate.evidence or {}).get("canaryStats") or {})
    return CanaryStatusResponse(
        candidate_id=candidate.id,
        skill_id=skill_id,
        status=candidate.status,
        canary_score=candidate.canary_score,
        feedback_count=int(stats.get("feedbackCount", 0)),
        exposures=int(stats.get("exposures", 0)),
        average_explicit_score=float(stats.get("averageExplicitScore", 0.0)),
        average_error_rate_rise=float(stats.get("averageErrorRateRise", 0.0)),
        average_adoption_rate=float(stats.get("averageAdoptionRate", 0.0)),
    )

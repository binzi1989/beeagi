from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_pipeline
from app.api.security import require_control_plane_api_key
from app.schemas.evolution import (
    AutoPromoteRequest,
    AutoPromoteResponse,
    AutonomousLifeControlRequest,
    AutonomousLifeStatus,
    CandidateStatusAuditView,
    EvolutionEventView,
    EvolutionTelemetryResponse,
    HardeningReportResponse,
    ScoutPatrolRequest,
    ScoutPatrolResponse,
    ScoutPheromoneView,
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


@router.get("/pheromones", response_model=list[ScoutPheromoneView], response_model_by_alias=True)
def list_scout_pheromones(
    limit: int = Query(default=100, ge=1, le=500),
    intent_cluster: str | None = Query(default=None, alias="intentCluster"),
    only_active: bool = Query(default=True, alias="onlyActive"),
    pipeline: PipelineService = Depends(get_pipeline),
) -> list[ScoutPheromoneView]:
    rows = pipeline.list_scout_pheromones(
        limit=limit,
        intent_cluster=intent_cluster,
        only_active=only_active,
    )
    return [ScoutPheromoneView.model_validate(item) for item in rows]


@router.post("/scout-patrol", response_model=ScoutPatrolResponse, response_model_by_alias=True)
def run_scout_patrol(
    payload: ScoutPatrolRequest,
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
) -> ScoutPatrolResponse:
    result = pipeline.run_scout_patrol(sample_size=payload.sample_size)
    return ScoutPatrolResponse.model_validate(result)


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


@router.get("/telemetry", response_model=EvolutionTelemetryResponse, response_model_by_alias=True)
def evolution_telemetry(
    window_minutes: int = Query(default=180, ge=30, le=1440, alias="windowMinutes"),
    pipeline: PipelineService = Depends(get_pipeline),
) -> EvolutionTelemetryResponse:
    payload = pipeline.build_evolution_telemetry(window_minutes=window_minutes)
    return EvolutionTelemetryResponse.model_validate(payload)


@router.get("/life", response_model=AutonomousLifeStatus, response_model_by_alias=True)
def get_autonomous_life_status(request: Request) -> AutonomousLifeStatus:
    engine = getattr(request.app.state, "autonomous_life", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="autonomous life engine is unavailable")
    return AutonomousLifeStatus.model_validate(engine.snapshot())


@router.post("/life/control", response_model=AutonomousLifeStatus, response_model_by_alias=True)
async def control_autonomous_life(
    payload: AutonomousLifeControlRequest,
    request: Request,
    _: None = Depends(require_control_plane_api_key),
) -> AutonomousLifeStatus:
    engine = getattr(request.app.state, "autonomous_life", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="autonomous life engine is unavailable")

    action = payload.action.strip().lower()
    if action == "touch":
        engine.touch(payload.reason)
    elif action == "cycle-now":
        await engine.run_cycle_now(reason=payload.reason)
    else:
        raise HTTPException(status_code=400, detail="action must be 'touch' or 'cycle-now'")
    return AutonomousLifeStatus.model_validate(engine.snapshot())

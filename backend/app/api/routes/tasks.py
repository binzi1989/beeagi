from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_pipeline
from app.api.security import require_control_plane_api_key
from app.core.config import get_settings
from app.schemas.feedback import AutoFeedbackRequest, AutoFeedbackResponse, FeedbackRequest
from app.schemas.tasks import TaskCreateRequest, TaskDetail
from app.services.pipeline import PipelineService
from worker.tasks import execute_task as execute_task_async

router = APIRouter()
settings = get_settings()


@router.post("", response_model=TaskDetail, response_model_by_alias=True)
def create_task(
    payload: TaskCreateRequest,
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
    x_user: str = Header(default="anonymous", alias="X-User"),
) -> TaskDetail:
    run_immediately = (not payload.run_async) or (payload.run_async and not settings.celery_enabled)
    task = pipeline.create_task(payload.spec, created_by=x_user, run_immediately=run_immediately)
    if payload.run_async and settings.celery_enabled:
        execute_task_async.delay(task.id)
    return TaskDetail.model_validate(task)


@router.get("/{task_id}", response_model=TaskDetail, response_model_by_alias=True)
def get_task(task_id: str, pipeline: PipelineService = Depends(get_pipeline)) -> TaskDetail:
    try:
        task = pipeline.get_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TaskDetail.model_validate(task)


@router.post("/{task_id}/feedback", response_model=dict, response_model_by_alias=True)
def submit_feedback(
    task_id: str,
    payload: FeedbackRequest,
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
    x_user: str = Header(default="anonymous", alias="X-User"),
) -> dict:
    try:
        candidate = pipeline.submit_feedback(task_id, payload.feedback, created_by=x_user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "candidateId": candidate.id,
        "skillId": candidate.skill_id,
        "status": candidate.status,
        "shadowScore": candidate.shadow_score,
        "canaryScore": candidate.canary_score,
    }


@router.post("/{task_id}/auto-feedback", response_model=AutoFeedbackResponse, response_model_by_alias=True)
def auto_feedback(
    task_id: str,
    payload: AutoFeedbackRequest,
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
    x_user: str = Header(default="anonymous", alias="X-User"),
) -> AutoFeedbackResponse:
    try:
        result = pipeline.auto_feedback_from_conversation(
            task_id=task_id,
            turns=payload.turns,
            created_by=x_user,
            only_if_missing=payload.only_if_missing,
            source=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AutoFeedbackResponse.model_validate(result)

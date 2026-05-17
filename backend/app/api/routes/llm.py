from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import get_pipeline
from app.api.security import require_control_plane_api_key
from app.schemas.llm import LlmConfigUpdateRequest, LlmConfigView, LlmTokenStatsResponse
from app.services.pipeline import PipelineService

router = APIRouter()


@router.get("/config", response_model=LlmConfigView, response_model_by_alias=True)
def get_llm_config(
    request: Request,
    _: None = Depends(require_control_plane_api_key),
) -> LlmConfigView:
    model_router = request.app.state.model_router
    return LlmConfigView.model_validate(model_router.get_runtime_config())


@router.put("/config", response_model=LlmConfigView, response_model_by_alias=True)
def update_llm_config(
    payload: LlmConfigUpdateRequest,
    request: Request,
    _: None = Depends(require_control_plane_api_key),
) -> LlmConfigView:
    model_router = request.app.state.model_router
    try:
        updated = model_router.update_runtime_config(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LlmConfigView.model_validate(updated)


@router.get("/token-stats", response_model=LlmTokenStatsResponse, response_model_by_alias=True)
def get_token_stats(
    limit: int = Query(default=300, ge=1, le=5000),
    pipeline: PipelineService = Depends(get_pipeline),
    _: None = Depends(require_control_plane_api_key),
) -> LlmTokenStatsResponse:
    stats = pipeline.get_token_statistics(limit=limit)
    return LlmTokenStatsResponse.model_validate(stats)

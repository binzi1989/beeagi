from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import ApiModel


class SkillCard(ApiModel):
    id: str
    name: str
    description: str
    version: int
    io_schema: dict[str, Any]
    permissions: dict[str, Any]
    cost_budget: dict[str, Any]
    config: dict[str, Any]
    status: str
    updated_at: datetime


class SkillDelta(ApiModel):
    target_skill: str
    change_type: str
    patch: dict[str, Any]
    evidence: dict[str, Any]


class CreateCandidateRequest(ApiModel):
    delta: SkillDelta
    shadow_score: float | None = None
    canary_score: float | None = None


class CandidateResponse(ApiModel):
    id: str
    skill_id: str
    status: str
    shadow_score: float
    canary_score: float | None = None
    proposed_delta: dict[str, Any]
    evidence: dict[str, Any]
    created_at: datetime


class PromoteRequest(ApiModel):
    candidate_id: str
    approved_by: str = "queen"


class RollbackRequest(ApiModel):
    reason: str
    requested_by: str = "queen"


class ShadowReplayRequest(ApiModel):
    sample_size: int = Field(default=50, ge=1, le=500)


class ShadowReplayResponse(ApiModel):
    candidate_id: str
    skill_id: str
    status: str
    shadow_score: float
    sample_size: int
    baseline_average: float
    candidate_average: float
    improvement_ratio: float


class CanaryStatusResponse(ApiModel):
    candidate_id: str
    skill_id: str
    status: str
    canary_score: float | None
    feedback_count: int
    exposures: int
    average_explicit_score: float
    average_error_rate_rise: float
    average_adoption_rate: float

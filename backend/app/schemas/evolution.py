from datetime import datetime
from typing import Any

from app.schemas.common import ApiModel


class EvolutionDecision(ApiModel):
    candidate_id: str
    shadow_score: float
    canary_score: float | None
    decision: str
    reason: str


class EvolutionEventView(ApiModel):
    id: str
    topic: str
    payload: dict[str, Any]
    created_at: datetime


class CandidateStatusAuditView(ApiModel):
    id: str
    candidate_id: str
    skill_id: str
    from_status: str | None
    to_status: str
    decision: str | None
    reason: str | None
    actor: str
    context: dict[str, Any]
    created_at: datetime


class AutoPromoteRequest(ApiModel):
    limit: int = 20
    approved_by: str = "queen-auto"


class AutoPromoteOutcome(ApiModel):
    candidate_id: str
    skill_id: str
    status: str
    previous_status: str | None = None
    decision: str
    reason: str


class AutoPromoteResponse(ApiModel):
    total: int
    promoted: int
    rolled_back: int
    validated: int
    rejected: int
    skipped: int
    outcomes: list[AutoPromoteOutcome]


class HardeningCheck(ApiModel):
    id: str
    level: str
    message: str


class HardeningSummary(ApiModel):
    skill_count: int
    candidate_count: int
    recent_event_count: int
    recent_audit_count: int
    waiting_validated_candidates: int
    event_bus_backend: str
    api_key_enabled: bool


class HardeningReportResponse(ApiModel):
    generated_at: datetime
    overall: str
    summary: HardeningSummary
    checks: list[HardeningCheck]
    missing_topics: list[str]

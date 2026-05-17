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


class ScoutPheromoneView(ApiModel):
    id: str
    intent_cluster: str
    source: str
    route: str
    novelty: float
    reliability: float
    cost: float
    reward: float
    strength: float
    ttl_seconds: int
    usage_count: int
    success_count: int
    failure_count: int
    notes: str | None = None
    metadata_json: dict[str, Any]
    last_seen_at: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ScoutPatrolRequest(ApiModel):
    sample_size: int = 30


class ScoutPatrolResponse(ApiModel):
    sample_size: int
    sampled_tasks: int
    touched_clusters: list[str]
    deposited: int
    evaporated: int
    expired: int


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


class EvolutionTelemetryRoles(ApiModel):
    scout_events_60m: int
    worker_events_60m: int
    worm_events_60m: int
    queen_events_60m: int
    feedback_events_60m: int
    system_events_60m: int


class EvolutionTelemetryFunnel(ApiModel):
    proposed: int
    validated: int
    promoted: int
    rejected: int
    rolled_back: int
    total_candidates: int
    validation_ratio: float
    promotion_ratio: float
    rollback_ratio: float


class EvolutionTelemetryTasks(ApiModel):
    total_24h: int
    completed_24h: int
    failed_24h: int
    success_rate_24h: float
    avg_duration_ms_24h: float
    tasks_per_hour_24h: float


class EvolutionTelemetrySpeed(ApiModel):
    events_last_5m: int
    events_per_minute_5m: float
    proposals_last_60m: int
    promotions_last_60m: int
    rollbacks_last_60m: int
    patrols_last_60m: int
    avg_decision_minutes_24h: float
    progress_score: float
    velocity_score: float


class EvolutionTelemetryPoint(ApiModel):
    bucket: str
    events: int
    promotions: int
    proposals: int


class EvolutionTelemetryResponse(ApiModel):
    generated_at: datetime
    window_minutes: int
    active_pheromones: int
    roles: EvolutionTelemetryRoles
    funnel: EvolutionTelemetryFunnel
    tasks: EvolutionTelemetryTasks
    speed: EvolutionTelemetrySpeed
    timeline: list[EvolutionTelemetryPoint]

from datetime import datetime
from typing import Literal
from typing import Any

from pydantic import Field

from app.schemas.common import ApiModel


class TaskSpec(ApiModel):
    goal: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    context_refs: list[str] = Field(default_factory=list)
    quality_target: float = 0.85
    priority: int = 3


class TaskCreateRequest(ApiModel):
    spec: TaskSpec
    run_async: bool = False


class TaskSummary(ApiModel):
    id: str
    goal: str
    status: str
    priority: int
    quality_target: float
    created_by: str
    created_at: datetime
    updated_at: datetime


class TaskDetail(TaskSummary):
    scout_report: dict[str, Any] | None = None
    plan_graph: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None


class DeliverableOpenRequest(ApiModel):
    mode: Literal["file", "folder"] = "file"
    artifact_path: str | None = None


class DeliverableOpenResponse(ApiModel):
    task_id: str
    mode: Literal["file", "folder"]
    opened_path: str

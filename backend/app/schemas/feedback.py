from typing import Any

from pydantic import Field

from app.schemas.common import ApiModel


class FeedbackPacket(ApiModel):
    explicit_score: float | None = None
    corrections: str | None = None
    implicit_signals: dict[str, Any]


class FeedbackRequest(ApiModel):
    feedback: FeedbackPacket


class ConversationTurn(ApiModel):
    role: str
    content: str


class AutoFeedbackRequest(ApiModel):
    turns: list[ConversationTurn] = Field(default_factory=list)
    only_if_missing: bool = True
    source: str = "auto-inferred"


class AutoFeedbackResponse(ApiModel):
    status: str
    reason: str | None = None
    source: str
    feedback_id: str | None = None
    candidate_id: str | None = None
    skill_id: str | None = None
    candidate_status: str | None = None
    inferred_feedback: FeedbackPacket | None = None

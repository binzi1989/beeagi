from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


class TaskStatus(str, enum.Enum):
    queued = "queued"
    planned = "planned"
    running = "running"
    completed = "completed"
    failed = "failed"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    context_refs: Mapped[list] = mapped_column(JSON, default=list)
    quality_target: Mapped[float] = mapped_column(Float, default=0.85)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    created_by: Mapped[str] = mapped_column(String(64), default="anonymous")
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.queued.value)

    scout_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plan_graph: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    feedback_entries: Mapped[list["TaskFeedback"]] = relationship(
        "TaskFeedback",
        back_populates="task",
        cascade="all, delete-orphan",
    )

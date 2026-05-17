from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


class SkillStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"


class CandidateStatus(str, enum.Enum):
    proposed = "proposed"
    validated = "validated"
    promoted = "promoted"
    rejected = "rejected"
    rolled_back = "rolled_back"


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)

    io_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_budget: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(32), default=SkillStatus.active.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    candidates: Mapped[list["SkillCandidate"]] = relationship(
        "SkillCandidate",
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class SkillCandidate(Base):
    __tablename__ = "skill_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default=CandidateStatus.proposed.value)

    proposed_delta: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    shadow_score: Mapped[float] = mapped_column(Float, default=0.0)
    canary_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    skill: Mapped[Skill] = relationship("Skill", back_populates="candidates")

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.skill import Skill


DEFAULT_SKILLS = [
    {
        "id": "plan_graph_builder",
        "name": "Plan Graph Builder",
        "description": "Transforms goals into executable plan graphs.",
        "version": 1,
        "io_schema": {"input": ["goal", "constraints"], "output": ["planGraph"]},
        "permissions": {"network": False, "filesystem": "read"},
        "cost_budget": {"maxTokens": 6000},
        "config": {"strategy": "tree_of_thought"},
    },
    {
        "id": "execution_synthesizer",
        "name": "Execution Synthesizer",
        "description": "Executes tool output synthesis with structured response generation.",
        "version": 1,
        "io_schema": {"input": ["planGraph", "context"], "output": ["resultPayload"]},
        "permissions": {"network": True, "filesystem": "read_write"},
        "cost_budget": {"maxTokens": 12000},
        "config": {"strategy": "tool_first"},
    },
]


def seed_default_skills(db: Session) -> None:
    existing = {s.id for s in db.query(Skill).all()}
    for item in DEFAULT_SKILLS:
        if item["id"] in existing:
            continue
        db.add(Skill(**item))
    db.commit()

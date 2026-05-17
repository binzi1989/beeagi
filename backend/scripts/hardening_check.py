from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.event_bus import build_event_bus
from app.services.model_router import ModelRouter
from app.services.pipeline import PipelineService


def main() -> None:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)

    pipeline = PipelineService(
        session_factory=SessionLocal,
        event_bus=build_event_bus(settings.redis_url),
        settings=settings,
        model_router=ModelRouter(settings),
    )
    report = pipeline.build_hardening_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

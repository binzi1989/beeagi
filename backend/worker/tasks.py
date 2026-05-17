from worker.celery_app import celery_app

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.event_bus import build_event_bus
from app.services.model_router import ModelRouter
from app.services.pipeline import PipelineService

settings = get_settings()


@celery_app.task(name="tasks.execute_task")
def execute_task(task_id: str) -> dict:
    pipeline = PipelineService(
        session_factory=SessionLocal,
        event_bus=build_event_bus(settings.redis_url),
        settings=settings,
        model_router=ModelRouter(settings),
    )
    task = pipeline.execute_task(task_id)
    return {"taskId": task.id, "status": task.status}

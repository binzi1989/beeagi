from fastapi import APIRouter

from app.api.routes.evolution import router as evolution_router
from app.api.routes.health import router as health_router
from app.api.routes.llm import router as llm_router
from app.api.routes.skills import router as skills_router
from app.api.routes.tasks import router as tasks_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(skills_router, prefix="/skills", tags=["skills"])
api_router.include_router(evolution_router, prefix="/evolution", tags=["evolution"])
api_router.include_router(llm_router, prefix="/llm", tags=["llm"])

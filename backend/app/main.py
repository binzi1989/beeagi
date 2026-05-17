from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.artifact_store import ArtifactStore
from app.services.autonomous_life import AutonomousLifeEngine
from app.services.event_bus import build_event_bus
from app.services.model_router import ModelRouter
from app.services.pipeline import PipelineService
from app.services.skill_registry import seed_default_skills

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_default_skills(db)
    app.state.event_bus = build_event_bus(settings.redis_url)
    app.state.artifact_store = ArtifactStore(settings.artifact_dir)
    app.state.model_router = ModelRouter(settings)
    app.state.pipeline = PipelineService(
        session_factory=SessionLocal,
        event_bus=app.state.event_bus,
        settings=settings,
        artifact_store=app.state.artifact_store,
        model_router=app.state.model_router,
    )
    app.state.autonomous_life = AutonomousLifeEngine(
        pipeline=app.state.pipeline,
        settings=settings,
    )
    app.state.pipeline.set_life_signal(app.state.autonomous_life.touch)
    await app.state.autonomous_life.start()
    yield
    await app.state.autonomous_life.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
    allow_credentials=settings.cors_allow_credentials,
)
app.include_router(api_router)

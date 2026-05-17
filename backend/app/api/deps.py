from fastapi import Request

from app.services.pipeline import PipelineService


def get_pipeline(request: Request) -> PipelineService:
    return request.app.state.pipeline

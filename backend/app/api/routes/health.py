from fastapi import APIRouter

from backend.app.application.health import HealthService
from backend.app.schemas.health import HealthResponse


def create_health_router(service: HealthService) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health", response_model=HealthResponse)
    async def get_health() -> HealthResponse:
        return HealthResponse.model_validate(service.get_health())

    return router

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.health import create_health_router
from backend.app.application.health import HealthService
from backend.app.core.config import get_settings
from backend.app.core.errors import configure_error_handling
from backend.app.core.version import APP_VERSION


def create_app(health_service: HealthService | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=APP_VERSION)
    configure_error_handling(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type", "X-Trace-ID"],
    )
    service = health_service or HealthService(version=APP_VERSION)
    app.include_router(create_health_router(service))
    return app


app = create_app()

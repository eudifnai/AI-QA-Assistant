from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.dependencies import create_session_auth_dependency
from backend.app.api.routes.health import create_health_router
from backend.app.application.health import HealthService
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import configure_error_handling
from backend.app.core.version import APP_VERSION


def create_app(
    health_service: HealthService | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    configured_settings = settings or get_settings()
    session_auth = create_session_auth_dependency(configured_settings.session_token)
    app = FastAPI(
        title=configured_settings.app_name,
        version=APP_VERSION,
        dependencies=[Depends(session_auth)],
    )
    configure_error_handling(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured_settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept", "Authorization", "Content-Type", "X-Trace-ID"],
    )
    service = health_service or HealthService(version=APP_VERSION)
    app.include_router(create_health_router(service))
    return app


app = create_app()

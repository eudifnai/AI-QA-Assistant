from fastapi import APIRouter, status

from backend.app.application.maintenance import MaintenanceUseCases
from backend.app.schemas.maintenance import BackupResponse, DiagnosticsResponse


def create_maintenance_router(service: MaintenanceUseCases) -> APIRouter:
    router = APIRouter(tags=["maintenance"])

    @router.get("/api/diagnostics", response_model=DiagnosticsResponse)
    def get_diagnostics() -> DiagnosticsResponse:
        return DiagnosticsResponse.from_domain(service.diagnostics())

    @router.get("/api/backups", response_model=list[BackupResponse])
    def list_backups() -> list[BackupResponse]:
        return [BackupResponse.from_domain(item) for item in service.list_backups()]

    @router.post(
        "/api/backups",
        response_model=BackupResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_backup() -> BackupResponse:
        return BackupResponse.from_domain(service.create_backup())

    return router

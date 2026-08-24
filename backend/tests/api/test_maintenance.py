from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from fastapi.testclient import TestClient

from backend.app.application.maintenance import MaintenanceUseCases
from backend.app.core.errors import AppError
from backend.app.domain.maintenance import BackupInfo, DatabaseDiagnostics, DiagnosticsReport
from backend.app.main import create_app

NOW = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
BACKUP = BackupInfo(path=Path("C:/data/backups/app.db"), created_at=NOW, size_bytes=1024)
REPORT = DiagnosticsReport(
    app_version="0.1.0",
    python_version="3.12.11",
    platform="Windows-11",
    api_host="127.0.0.1",
    database=DatabaseDiagnostics(
        database_path=Path("C:/data/app.db"),
        backup_directory=Path("C:/data/backups"),
        database_size_bytes=2048,
        database_integrity="ok",
        database_revision="20260809_0003",
        workspace_count=2,
        backup_count=1,
    ),
)


class StubMaintenanceService(MaintenanceUseCases):
    def diagnostics(self) -> DiagnosticsReport:
        return REPORT

    def list_backups(self) -> list[BackupInfo]:
        return [BACKUP]

    def create_backup(self, created_at: datetime | None = None) -> BackupInfo:
        return BACKUP


class FailingMaintenanceService(StubMaintenanceService):
    def create_backup(self, created_at: datetime | None = None) -> NoReturn:
        raise AppError(code="BACKUP_UNAVAILABLE", message="无法创建数据库备份。", status_code=503)


class CrashingMaintenanceService(StubMaintenanceService):
    def diagnostics(self) -> NoReturn:
        raise RuntimeError("sensitive diagnostics detail")


def test_diagnostics_returns_safe_local_state() -> None:
    app = create_app(maintenance_service=StubMaintenanceService())

    with TestClient(app) as client:
        response = client.get("/api/diagnostics")

    assert response.status_code == 200
    assert response.json()["database_integrity"] == "ok"
    assert response.json()["api_host"] == "127.0.0.1"


def test_list_and_create_backups() -> None:
    app = create_app(maintenance_service=StubMaintenanceService())

    with TestClient(app) as client:
        listed = client.get("/api/backups")
        created = client.post("/api/backups")

    assert listed.status_code == 200
    assert listed.json()[0]["file_name"] == "app.db"
    assert created.status_code == 201
    assert created.json()["size_bytes"] == 1024


def test_backup_maps_business_failure() -> None:
    app = create_app(maintenance_service=FailingMaintenanceService())

    with TestClient(app) as client:
        response = client.post("/api/backups")

    assert response.status_code == 503
    assert response.json()["code"] == "BACKUP_UNAVAILABLE"


def test_diagnostics_unexpected_failure_is_redacted() -> None:
    app = create_app(maintenance_service=CrashingMaintenanceService())

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/diagnostics")

    assert response.status_code == 500
    assert "sensitive diagnostics detail" not in response.text

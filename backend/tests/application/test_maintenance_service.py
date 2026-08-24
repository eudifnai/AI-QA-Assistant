from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.application.maintenance import (
    MaintenanceService,
    MaintenanceStorage,
    MaintenanceStorageError,
)
from backend.app.core.errors import AppError
from backend.app.domain.maintenance import BackupInfo, DatabaseDiagnostics

NOW = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
BACKUP = BackupInfo(path=Path("C:/backups/app.db"), created_at=NOW, size_bytes=1024)
DATABASE = DatabaseDiagnostics(
    database_path=Path("C:/data/app.db"),
    backup_directory=Path("C:/data/backups"),
    database_size_bytes=2048,
    database_integrity="ok",
    database_revision="20260809_0003",
    workspace_count=2,
    backup_count=1,
)


class StubMaintenanceStorage(MaintenanceStorage):
    def list_backups(self) -> list[BackupInfo]:
        return [BACKUP]

    def create_backup(self, created_at: datetime) -> BackupInfo:
        return BACKUP

    def diagnostics(self) -> DatabaseDiagnostics:
        return DATABASE


class FailingMaintenanceStorage(StubMaintenanceStorage):
    def create_backup(self, created_at: datetime) -> BackupInfo:
        raise MaintenanceStorageError("sensitive sqlite detail")


def test_maintenance_service_aggregates_safe_system_diagnostics() -> None:
    service = MaintenanceService(StubMaintenanceStorage(), app_version="0.1.0")

    result = service.diagnostics()

    assert result.app_version == "0.1.0"
    assert result.api_host == "127.0.0.1"
    assert result.database == DATABASE
    assert result.python_version
    assert result.platform


def test_backup_failure_maps_to_stable_error() -> None:
    service = MaintenanceService(FailingMaintenanceStorage(), app_version="0.1.0")

    with pytest.raises(AppError) as raised:
        service.create_backup(NOW)

    assert raised.value.code == "BACKUP_UNAVAILABLE"
    assert raised.value.status_code == 503

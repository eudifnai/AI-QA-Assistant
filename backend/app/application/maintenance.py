import platform as system_platform
from datetime import UTC, datetime
from typing import Protocol

from backend.app.core.errors import AppError
from backend.app.core.network import API_LOOPBACK_HOST
from backend.app.domain.maintenance import BackupInfo, DatabaseDiagnostics, DiagnosticsReport


class MaintenanceStorageError(Exception):
    pass


class MaintenanceStorage(Protocol):
    def list_backups(self) -> list[BackupInfo]: ...

    def create_backup(self, created_at: datetime) -> BackupInfo: ...

    def diagnostics(self) -> DatabaseDiagnostics: ...


class MaintenanceUseCases(Protocol):
    def diagnostics(self) -> DiagnosticsReport: ...

    def list_backups(self) -> list[BackupInfo]: ...

    def create_backup(self, created_at: datetime | None = None) -> BackupInfo: ...


class MaintenanceService:
    def __init__(self, storage: MaintenanceStorage, *, app_version: str) -> None:
        self._storage = storage
        self._app_version = app_version

    def diagnostics(self) -> DiagnosticsReport:
        try:
            database = self._storage.diagnostics()
        except MaintenanceStorageError as exception:
            raise self._unavailable_error("无法读取本地诊断信息。") from exception
        return DiagnosticsReport(
            app_version=self._app_version,
            python_version=system_platform.python_version(),
            platform=system_platform.platform(),
            api_host=API_LOOPBACK_HOST,
            database=database,
        )

    def list_backups(self) -> list[BackupInfo]:
        try:
            return self._storage.list_backups()
        except MaintenanceStorageError as exception:
            raise self._unavailable_error("无法读取数据库备份列表。") from exception

    def create_backup(self, created_at: datetime | None = None) -> BackupInfo:
        try:
            return self._storage.create_backup(created_at or datetime.now(UTC))
        except MaintenanceStorageError as exception:
            raise self._unavailable_error("无法创建数据库备份。") from exception

    @staticmethod
    def _unavailable_error(message: str) -> AppError:
        return AppError(code="BACKUP_UNAVAILABLE", message=message, status_code=503)

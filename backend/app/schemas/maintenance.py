from datetime import datetime

from pydantic import BaseModel

from backend.app.domain.maintenance import BackupInfo, DiagnosticsReport


class BackupResponse(BaseModel):
    file_name: str
    path: str
    created_at: datetime
    size_bytes: int

    @classmethod
    def from_domain(cls, backup: BackupInfo) -> "BackupResponse":
        return cls(
            file_name=backup.path.name,
            path=str(backup.path),
            created_at=backup.created_at,
            size_bytes=backup.size_bytes,
        )


class DiagnosticsResponse(BaseModel):
    app_version: str
    python_version: str
    platform: str
    api_host: str
    database_path: str
    backup_directory: str
    database_size_bytes: int
    database_integrity: str
    database_revision: str | None
    workspace_count: int
    backup_count: int

    @classmethod
    def from_domain(cls, report: DiagnosticsReport) -> "DiagnosticsResponse":
        return cls(
            app_version=report.app_version,
            python_version=report.python_version,
            platform=report.platform,
            api_host=report.api_host,
            database_path=str(report.database.database_path),
            backup_directory=str(report.database.backup_directory),
            database_size_bytes=report.database.database_size_bytes,
            database_integrity=report.database.database_integrity,
            database_revision=report.database.database_revision,
            workspace_count=report.database.workspace_count,
            backup_count=report.database.backup_count,
        )

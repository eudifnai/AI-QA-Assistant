from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BackupInfo:
    path: Path
    created_at: datetime
    size_bytes: int


@dataclass(frozen=True, slots=True)
class DatabaseDiagnostics:
    database_path: Path
    backup_directory: Path
    database_size_bytes: int
    database_integrity: str
    database_revision: str | None
    workspace_count: int
    backup_count: int


@dataclass(frozen=True, slots=True)
class DiagnosticsReport:
    app_version: str
    python_version: str
    platform: str
    api_host: str
    database: DatabaseDiagnostics

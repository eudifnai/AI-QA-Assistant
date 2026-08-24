import os
import sqlite3
from contextlib import closing, suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url

from backend.app.application.maintenance import MaintenanceStorageError
from backend.app.domain.maintenance import BackupInfo, DatabaseDiagnostics

BACKUP_FILE_PREFIX = "ai-qa-assistant-"


class SqliteMaintenanceStorage:
    def __init__(self, database_url: str) -> None:
        url = make_url(database_url)
        if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
            raise MaintenanceStorageError("maintenance requires a file-backed SQLite database")
        self._database_path = Path(url.database).resolve(strict=False)
        self._backup_directory = (self._database_path.parent / "backups").resolve(strict=False)

    def list_backups(self) -> list[BackupInfo]:
        try:
            if not self._backup_directory.exists():
                return []
            backups = [
                self._backup_info(path)
                for path in self._backup_directory.glob(f"{BACKUP_FILE_PREFIX}*.db")
                if path.is_file() and path.resolve().parent == self._backup_directory
            ]
            return sorted(backups, key=lambda item: item.created_at, reverse=True)
        except OSError as exception:
            raise MaintenanceStorageError("unable to list backups") from exception

    def create_backup(self, created_at: datetime) -> BackupInfo:
        if not self._database_path.is_file():
            raise MaintenanceStorageError("database file does not exist")
        timestamp = created_at.astimezone(UTC)
        file_name = (
            f"{BACKUP_FILE_PREFIX}{timestamp.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}.db"
        )
        temporary: Path | None = None
        try:
            self._backup_directory.mkdir(parents=True, exist_ok=True)
            destination = (self._backup_directory / file_name).resolve(strict=False)
            if destination.parent != self._backup_directory:
                raise MaintenanceStorageError("backup path escaped backup directory")
            temporary = destination.with_suffix(".tmp")
            with (
                closing(sqlite3.connect(self._database_path)) as source,
                closing(sqlite3.connect(temporary)) as target,
            ):
                source.backup(target, pages=256)
                integrity = target.execute("PRAGMA integrity_check").fetchone()
                if integrity != ("ok",):
                    raise MaintenanceStorageError("backup integrity check failed")
            temporary.replace(destination)
            os.utime(destination, (timestamp.timestamp(), timestamp.timestamp()))
            return self._backup_info(destination)
        except (OSError, sqlite3.Error) as exception:
            raise MaintenanceStorageError("unable to create backup") from exception
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)

    def diagnostics(self) -> DatabaseDiagnostics:
        try:
            if not self._database_path.is_file():
                raise MaintenanceStorageError("database file does not exist")
            with sqlite3.connect(self._database_path) as connection:
                integrity_row = connection.execute("PRAGMA quick_check").fetchone()
                revision = self._single_value(
                    connection,
                    "SELECT version_num FROM alembic_version LIMIT 1",
                )
                workspace_count = self._single_value(
                    connection,
                    "SELECT COUNT(*) FROM workspaces",
                )
            return DatabaseDiagnostics(
                database_path=self._database_path,
                backup_directory=self._backup_directory,
                database_size_bytes=self._database_path.stat().st_size,
                database_integrity=str(integrity_row[0]) if integrity_row else "unknown",
                database_revision=None if revision is None else str(revision),
                workspace_count=workspace_count if isinstance(workspace_count, int) else 0,
                backup_count=len(self.list_backups()),
            )
        except (OSError, sqlite3.Error, ValueError) as exception:
            raise MaintenanceStorageError("unable to inspect database") from exception

    @staticmethod
    def _single_value(connection: sqlite3.Connection, query: str) -> object | None:
        try:
            row = connection.execute(query).fetchone()
        except sqlite3.OperationalError:
            return None
        return None if row is None else row[0]

    @staticmethod
    def _backup_info(path: Path) -> BackupInfo:
        stat = path.stat()
        return BackupInfo(
            path=path.resolve(),
            created_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            size_bytes=stat.st_size,
        )

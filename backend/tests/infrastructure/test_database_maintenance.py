import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from backend.app.infrastructure.maintenance import SqliteMaintenanceStorage

NOW = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)


def create_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('20260809_0003')")
        connection.execute("CREATE TABLE workspaces (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO workspaces VALUES ('workspace-1')")


def test_online_backup_is_valid_and_listed_without_copying_workspace_files(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "app.db"
    workspace_file = tmp_path / "user-project.txt"
    workspace_file.write_text("private project data", encoding="utf-8")
    create_database(database_path)
    storage = SqliteMaintenanceStorage(f"sqlite:///{database_path.as_posix()}")

    backup = storage.create_backup(NOW)

    assert backup.path.parent == tmp_path / "backups"
    assert backup.path.name.startswith("ai-qa-assistant-20260810T020000")
    assert backup.size_bytes > 0
    assert storage.list_backups() == [backup]
    with sqlite3.connect(backup.path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT id FROM workspaces").fetchone() == ("workspace-1",)
    assert not (backup.path.parent / workspace_file.name).exists()


def test_diagnostics_reports_database_revision_and_counts(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    create_database(database_path)
    storage = SqliteMaintenanceStorage(f"sqlite:///{database_path.as_posix()}")
    storage.create_backup(NOW)

    diagnostics = storage.diagnostics()

    assert diagnostics.database_integrity == "ok"
    assert diagnostics.database_revision == "20260809_0003"
    assert diagnostics.workspace_count == 1
    assert diagnostics.backup_count == 1
    assert diagnostics.database_size_bytes > 0

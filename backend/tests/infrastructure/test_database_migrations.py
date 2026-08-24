import sqlite3
from pathlib import Path

from backend.app.infrastructure.database_migrations import upgrade_database


def test_upgrade_database_creates_latest_schema_in_app_data(tmp_path: Path) -> None:
    database_path = tmp_path / "profile%20data" / "ai_qa_assistant.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    upgrade_database(database_url)
    upgrade_database(database_url)

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        websocket_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(websocket_executions)").fetchall()
        }

    assert revision == ("20260816_0015",)
    assert "workspaces" in tables
    assert "assertion_results_json" in websocket_columns

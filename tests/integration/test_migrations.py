import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config(database_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def current_revision(database_path: Path) -> str | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def test_initial_migration_can_upgrade_downgrade_and_upgrade_again(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-test.db"
    config = migration_config(database_path)

    command.upgrade(config, "head")
    first_revision = current_revision(database_path)
    assert first_revision is not None

    command.downgrade(config, "base")
    assert current_revision(database_path) is None

    command.upgrade(config, "head")
    assert current_revision(database_path) == first_revision

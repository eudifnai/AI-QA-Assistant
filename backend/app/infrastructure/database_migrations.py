from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from backend.app.infrastructure.database import ensure_sqlite_parent


def bundled_migration_script_path() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if isinstance(frozen_root, str):
        return Path(frozen_root) / "backend" / "migrations"
    return Path(__file__).resolve().parents[2] / "migrations"


def upgrade_database(
    database_url: str,
    *,
    script_location: Path | None = None,
) -> None:
    migrations = (script_location or bundled_migration_script_path()).resolve()
    if not migrations.is_dir():
        raise RuntimeError("数据库迁移资源不可用。")

    ensure_sqlite_parent(database_url)
    config = Config()
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")

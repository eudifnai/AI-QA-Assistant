from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from backend.app.core.config import get_settings
from backend.app.infrastructure.analysis import (  # noqa: F401
    AnalysisCitationRecord,
    AnalysisIssueRecord,
    AnalysisRunRecord,
    AnalysisScoreRecord,
)
from backend.app.infrastructure.database import ensure_sqlite_parent
from backend.app.infrastructure.documents import (  # noqa: F401
    DocumentJobRecord,
    DocumentRecord,
    DocumentVersionRecord,
)
from backend.app.infrastructure.http_execution import (  # noqa: F401
    HttpEnvironmentRecord,
    HttpExecutionEventRecord,
    HttpExecutionRecord,
)
from backend.app.infrastructure.settings import AppSettingsRecord  # noqa: F401
from backend.app.infrastructure.websocket_execution import (  # noqa: F401
    WebSocketExecutionEventRecord,
    WebSocketExecutionRecord,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings_url = get_settings().database_url
configured_url = config.get_main_option("sqlalchemy.url") or settings_url
database_url = (
    configured_url
    if configured_url != "sqlite:///./.local-data/ai_qa_assistant.db"
    else settings_url
)
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
ensure_sqlite_parent(database_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

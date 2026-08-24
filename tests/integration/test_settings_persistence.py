from datetime import UTC, datetime
from pathlib import Path

from alembic import command

from backend.app.application.settings import SettingsService
from backend.app.domain.settings import ModelMode, ModelProvider, Theme
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.settings import SqlModelSettingsRepository
from tests.integration.test_migrations import migration_config


def test_settings_are_recovered_by_a_new_service_instance(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.db"
    command.upgrade(migration_config(database_path), "head")
    engine = create_database_engine(f"sqlite:///{database_path.as_posix()}")
    now = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)
    service = SettingsService(SqlModelSettingsRepository(engine), clock=lambda: now)

    saved = service.update(
        theme=Theme.DARK,
        model_mode=ModelMode.CLOUD,
        model_provider=ModelProvider.OPENAI_COMPATIBLE,
        model_name="qa-model",
        base_url="https://models.example.com/v1",
        cloud_data_consent=True,
    )

    restarted = SettingsService(SqlModelSettingsRepository(engine))
    assert restarted.get() == saved

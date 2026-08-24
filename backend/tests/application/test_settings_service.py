from datetime import UTC, datetime

from backend.app.application.settings import SettingsRepository, SettingsService
from backend.app.domain.settings import AppSettings, ModelMode, ModelProvider, Theme

NOW = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)


class MemorySettingsRepository(SettingsRepository):
    def __init__(self) -> None:
        self.value: AppSettings | None = None

    def get(self) -> AppSettings | None:
        return self.value

    def upsert(self, settings: AppSettings) -> AppSettings:
        self.value = settings
        return settings


def test_get_creates_persistent_privacy_safe_defaults() -> None:
    repository = MemorySettingsRepository()
    service = SettingsService(repository, clock=lambda: NOW)

    settings = service.get()

    assert settings.theme == Theme.LIGHT
    assert settings.model_mode == ModelMode.LOCAL
    assert settings.model_provider == ModelProvider.OLLAMA
    assert settings.model_name is None
    assert settings.base_url == "http://127.0.0.1:11434"
    assert settings.cloud_data_consent is False
    assert repository.value == settings


def test_update_persists_normalized_model_metadata_without_secret() -> None:
    repository = MemorySettingsRepository()
    service = SettingsService(repository, clock=lambda: NOW)

    settings = service.update(
        theme=Theme.DARK,
        model_mode=ModelMode.CLOUD,
        model_provider=ModelProvider.OPENAI_COMPATIBLE,
        model_name="  qa-model  ",
        base_url="https://models.example.com/v1/",
        cloud_data_consent=True,
    )

    assert settings.model_name == "qa-model"
    assert settings.base_url == "https://models.example.com/v1"
    assert repository.value == settings

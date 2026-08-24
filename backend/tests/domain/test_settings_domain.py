"""Domain tests for privacy-safe application settings."""

from datetime import UTC, datetime

import pytest

from backend.app.domain.settings import (
    ModelMode,
    ModelProvider,
    SettingsValidationError,
    Theme,
    build_app_settings,
)

NOW = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)


def test_local_model_configuration_accepts_only_loopback_ollama() -> None:
    settings = build_app_settings(
        theme=Theme.DARK,
        model_mode=ModelMode.LOCAL,
        model_provider=ModelProvider.OLLAMA,
        model_name="  qwen3:8b  ",
        base_url="http://127.0.0.1:11434/",
        cloud_data_consent=False,
        updated_at=NOW,
    )

    assert settings.model_name == "qwen3:8b"
    assert settings.base_url == "http://127.0.0.1:11434"


@pytest.mark.parametrize("base_url", ["http://192.168.1.20:11434", "https://example.com"])
def test_local_model_configuration_rejects_non_loopback_url(base_url: str) -> None:
    with pytest.raises(SettingsValidationError) as raised:
        build_app_settings(
            theme=Theme.LIGHT,
            model_mode=ModelMode.LOCAL,
            model_provider=ModelProvider.OLLAMA,
            model_name=None,
            base_url=base_url,
            cloud_data_consent=False,
            updated_at=NOW,
        )

    assert raised.value.code == "SETTINGS_MODEL_BASE_URL_INVALID"


def test_cloud_model_configuration_requires_https_and_explicit_consent() -> None:
    with pytest.raises(SettingsValidationError) as raised:
        build_app_settings(
            theme=Theme.LIGHT,
            model_mode=ModelMode.CLOUD,
            model_provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="qa-model",
            base_url="https://models.example.com/v1",
            cloud_data_consent=False,
            updated_at=NOW,
        )

    assert raised.value.code == "CLOUD_DATA_CONSENT_REQUIRED"


def test_model_mode_and_provider_must_match() -> None:
    with pytest.raises(SettingsValidationError) as raised:
        build_app_settings(
            theme=Theme.LIGHT,
            model_mode=ModelMode.CLOUD,
            model_provider=ModelProvider.OLLAMA,
            model_name=None,
            base_url="https://models.example.com/v1",
            cloud_data_consent=True,
            updated_at=NOW,
        )

    assert raised.value.code == "SETTINGS_MODEL_PROVIDER_INVALID"

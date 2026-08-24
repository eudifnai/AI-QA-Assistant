from datetime import UTC, datetime
from typing import NoReturn

from fastapi.testclient import TestClient

from backend.app.application.settings import SettingsUseCases
from backend.app.core.errors import AppError
from backend.app.domain.settings import AppSettings, ModelMode, ModelProvider, Theme
from backend.app.main import create_app

SETTINGS = AppSettings(
    theme=Theme.DARK,
    model_mode=ModelMode.LOCAL,
    model_provider=ModelProvider.OLLAMA,
    model_name="qwen3:8b",
    base_url="http://127.0.0.1:11434",
    cloud_data_consent=False,
    updated_at=datetime(2026, 8, 9, 3, 0, tzinfo=UTC),
)


class StubSettingsService(SettingsUseCases):
    def __init__(self) -> None:
        self.updated: dict[str, object] | None = None

    def get(self) -> AppSettings:
        return SETTINGS

    def update(self, **values: object) -> AppSettings:
        self.updated = values
        return SETTINGS


class FailingSettingsService(StubSettingsService):
    def update(self, **values: object) -> NoReturn:
        raise AppError(
            code="CLOUD_DATA_CONSENT_REQUIRED",
            message="启用云端模型前必须确认数据外发范围。",
            status_code=409,
        )


class CrashingSettingsService(StubSettingsService):
    def get(self) -> NoReturn:
        raise RuntimeError("sensitive settings detail")


def test_get_settings_returns_model_metadata_without_secret_fields() -> None:
    app = create_app(settings_service=StubSettingsService())

    with TestClient(app) as client:
        response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["model_provider"] == "ollama"
    assert "api_key" not in response.json()
    assert "credential" not in response.json()


def test_update_settings_validates_and_delegates() -> None:
    service = StubSettingsService()
    app = create_app(settings_service=service)
    payload = {
        "theme": "dark",
        "model_mode": "local",
        "model_provider": "ollama",
        "model_name": "qwen3:8b",
        "base_url": "http://127.0.0.1:11434",
        "cloud_data_consent": False,
    }

    with TestClient(app) as client:
        response = client.put("/api/settings", json=payload)

    assert response.status_code == 200
    assert service.updated == payload


def test_update_settings_rejects_secret_and_invalid_enum() -> None:
    app = create_app(settings_service=StubSettingsService())

    with TestClient(app) as client:
        response = client.put(
            "/api/settings",
            json={
                "theme": "unknown",
                "model_mode": "local",
                "model_provider": "ollama",
                "model_name": None,
                "base_url": "http://127.0.0.1:11434",
                "cloud_data_consent": False,
                "api_key": "must-not-be-accepted",
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_update_settings_maps_business_failure() -> None:
    app = create_app(settings_service=FailingSettingsService())

    with TestClient(app) as client:
        response = client.put(
            "/api/settings",
            json={
                "theme": "dark",
                "model_mode": "cloud",
                "model_provider": "openai_compatible",
                "model_name": "qa-model",
                "base_url": "https://models.example.com/v1",
                "cloud_data_consent": False,
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "CLOUD_DATA_CONSENT_REQUIRED"


def test_settings_unexpected_failure_is_redacted() -> None:
    app = create_app(settings_service=CrashingSettingsService())

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/settings")

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "sensitive settings detail" not in response.text

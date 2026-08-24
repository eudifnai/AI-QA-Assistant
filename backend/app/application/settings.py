from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from backend.app.core.errors import AppError
from backend.app.domain.settings import (
    AppSettings,
    ModelMode,
    ModelProvider,
    SettingsValidationError,
    Theme,
    build_app_settings,
)


class SettingsRepository(Protocol):
    def get(self) -> AppSettings | None: ...

    def upsert(self, settings: AppSettings) -> AppSettings: ...


class SettingsUseCases(Protocol):
    def get(self) -> AppSettings: ...

    def update(
        self,
        *,
        theme: Theme,
        model_mode: ModelMode,
        model_provider: ModelProvider,
        model_name: str | None,
        base_url: str,
        cloud_data_consent: bool,
    ) -> AppSettings: ...


class SettingsService:
    def __init__(
        self,
        repository: SettingsRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def get(self) -> AppSettings:
        settings = self._repository.get()
        if settings is not None:
            return settings
        return self._repository.upsert(
            build_app_settings(
                theme=Theme.LIGHT,
                model_mode=ModelMode.LOCAL,
                model_provider=ModelProvider.OLLAMA,
                model_name=None,
                base_url="http://127.0.0.1:11434",
                cloud_data_consent=False,
                updated_at=self._clock(),
            )
        )

    def update(
        self,
        *,
        theme: Theme,
        model_mode: ModelMode,
        model_provider: ModelProvider,
        model_name: str | None,
        base_url: str,
        cloud_data_consent: bool,
    ) -> AppSettings:
        try:
            settings = build_app_settings(
                theme=theme,
                model_mode=model_mode,
                model_provider=model_provider,
                model_name=model_name,
                base_url=base_url,
                cloud_data_consent=cloud_data_consent,
                updated_at=self._clock(),
            )
        except SettingsValidationError as exception:
            messages = {
                "CLOUD_DATA_CONSENT_REQUIRED": "启用云端模型前必须确认数据外发范围。",
                "SETTINGS_MODEL_BASE_URL_INVALID": "模型服务地址不符合当前模式的安全要求。",
                "SETTINGS_MODEL_NAME_INVALID": "模型名称长度不正确。",
                "SETTINGS_MODEL_PROVIDER_INVALID": "模型模式与 Provider 不匹配。",
            }
            raise AppError(
                code=exception.code,
                message=messages[exception.code],
                status_code=409 if exception.code == "CLOUD_DATA_CONSENT_REQUIRED" else 422,
            ) from exception
        return self._repository.upsert(settings)

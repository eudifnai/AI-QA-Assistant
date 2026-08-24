from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from ipaddress import ip_address
from urllib.parse import urlsplit

MAX_MODEL_NAME_LENGTH = 120
MAX_BASE_URL_LENGTH = 2048


class Theme(StrEnum):
    LIGHT = "light"
    DARK = "dark"


class ModelMode(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


class ModelProvider(StrEnum):
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"


class SettingsValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class AppSettings:
    theme: Theme
    model_mode: ModelMode
    model_provider: ModelProvider
    model_name: str | None
    base_url: str
    cloud_data_consent: bool
    updated_at: datetime


def _normalize_model_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_MODEL_NAME_LENGTH:
        raise SettingsValidationError("SETTINGS_MODEL_NAME_INVALID")
    return normalized


def _is_loopback_host(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _normalize_base_url(value: str, mode: ModelMode) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized or len(normalized) > MAX_BASE_URL_LENGTH:
        raise SettingsValidationError("SETTINGS_MODEL_BASE_URL_INVALID")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SettingsValidationError("SETTINGS_MODEL_BASE_URL_INVALID")
    if mode is ModelMode.LOCAL and not _is_loopback_host(parsed.hostname):
        raise SettingsValidationError("SETTINGS_MODEL_BASE_URL_INVALID")
    if mode is ModelMode.CLOUD and parsed.scheme != "https":
        raise SettingsValidationError("SETTINGS_MODEL_BASE_URL_INVALID")
    return normalized


def build_app_settings(
    *,
    theme: Theme,
    model_mode: ModelMode,
    model_provider: ModelProvider,
    model_name: str | None,
    base_url: str,
    cloud_data_consent: bool,
    updated_at: datetime,
) -> AppSettings:
    expected_provider = (
        ModelProvider.OLLAMA if model_mode is ModelMode.LOCAL else ModelProvider.OPENAI_COMPATIBLE
    )
    if model_provider is not expected_provider:
        raise SettingsValidationError("SETTINGS_MODEL_PROVIDER_INVALID")
    normalized_url = _normalize_base_url(base_url, model_mode)
    if model_mode is ModelMode.CLOUD and not cloud_data_consent:
        raise SettingsValidationError("CLOUD_DATA_CONSENT_REQUIRED")
    return AppSettings(
        theme=theme,
        model_mode=model_mode,
        model_provider=model_provider,
        model_name=_normalize_model_name(model_name),
        base_url=normalized_url,
        cloud_data_consent=cloud_data_consent if model_mode is ModelMode.CLOUD else False,
        updated_at=updated_at,
    )

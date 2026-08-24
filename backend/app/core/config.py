from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.core.network import API_LOOPBACK_HOST, validate_api_bind_host


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_QA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI QA Assistant"
    api_host: str = API_LOOPBACK_HOST
    api_port: int = Field(default=8765, ge=1024, le=65535)
    session_token: SecretStr | None = None
    database_url: str = "sqlite:///./.local-data/ai_qa_assistant.db"
    document_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    proto_max_bytes: int = Field(default=1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    document_parse_timeout_seconds: int = Field(default=60, ge=5, le=600)
    analysis_timeout_seconds: int = Field(default=300, ge=10, le=1800)
    model_request_timeout_seconds: int = Field(default=240, ge=5, le=1200)
    http_execution_timeout_seconds: int = Field(default=190, ge=5, le=300)
    websocket_execution_timeout_seconds: int = Field(default=130, ge=5, le=300)
    protobuf_execution_timeout_seconds: int = Field(default=70, ge=5, le=300)
    allowed_origins: tuple[str, ...] = (
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "app://ai-qa-assistant",
    )

    @field_validator("api_host")
    @classmethod
    def validate_api_host(cls, value: str) -> str:
        return validate_api_bind_host(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()

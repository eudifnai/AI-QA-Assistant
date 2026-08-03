from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_QA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI QA Assistant"
    api_host: Literal["127.0.0.1"] = "127.0.0.1"
    api_port: int = Field(default=8765, ge=1024, le=65535)
    database_url: str = "sqlite:///./.local-data/ai_qa_assistant.db"
    allowed_origins: tuple[str, ...] = (
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

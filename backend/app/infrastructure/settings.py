from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel

from backend.app.domain.settings import AppSettings, ModelMode, ModelProvider, Theme

SETTINGS_SINGLETON_ID = 1


class AppSettingsRecord(SQLModel, table=True):
    __tablename__ = "app_settings"

    id: int = Field(sa_column=Column(Integer, primary_key=True))
    theme: str = Field(sa_column=Column(String(16), nullable=False))
    model_mode: str = Field(sa_column=Column(String(16), nullable=False))
    model_provider: str = Field(sa_column=Column(String(32), nullable=False))
    model_name: str | None = Field(default=None, sa_column=Column(String(120), nullable=True))
    base_url: str = Field(sa_column=Column(String(2048), nullable=False))
    cloud_data_consent: bool = Field(sa_column=Column(Boolean, nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_domain(record: AppSettingsRecord) -> AppSettings:
    return AppSettings(
        theme=Theme(record.theme),
        model_mode=ModelMode(record.model_mode),
        model_provider=ModelProvider(record.model_provider),
        model_name=record.model_name,
        base_url=record.base_url,
        cloud_data_consent=record.cloud_data_consent,
        updated_at=_as_utc(record.updated_at),
    )


class SqlModelSettingsRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self) -> AppSettings | None:
        with Session(self._engine) as session:
            record = session.get(AppSettingsRecord, SETTINGS_SINGLETON_ID)
            return None if record is None else _to_domain(record)

    def upsert(self, settings: AppSettings) -> AppSettings:
        with Session(self._engine) as session:
            record = session.get(AppSettingsRecord, SETTINGS_SINGLETON_ID)
            if record is None:
                record = AppSettingsRecord(
                    id=SETTINGS_SINGLETON_ID,
                    theme=settings.theme.value,
                    model_mode=settings.model_mode.value,
                    model_provider=settings.model_provider.value,
                    model_name=settings.model_name,
                    base_url=settings.base_url,
                    cloud_data_consent=settings.cloud_data_consent,
                    updated_at=settings.updated_at,
                )
            else:
                record.theme = settings.theme.value
                record.model_mode = settings.model_mode.value
                record.model_provider = settings.model_provider.value
                record.model_name = settings.model_name
                record.base_url = settings.base_url
                record.cloud_data_consent = settings.cloud_data_consent
                record.updated_at = settings.updated_at
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_domain(record)

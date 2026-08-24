from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.settings import ModelMode, ModelProvider, Theme


class ModelCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=8, max_length=8192)


class ModelCredentialStatusResponse(BaseModel):
    configured: bool


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: Theme
    model_mode: ModelMode
    model_provider: ModelProvider
    model_name: str | None = Field(default=None, max_length=120)
    base_url: str = Field(min_length=1, max_length=2048)
    cloud_data_consent: bool


class SettingsResponse(SettingsUpdateRequest):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    updated_at: datetime

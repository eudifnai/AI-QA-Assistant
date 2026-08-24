from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceNameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("workspace name must not be blank")
        return normalized


class WorkspaceCreateRequest(WorkspaceNameRequest):
    path: str = Field(min_length=1, max_length=1024)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    path: str
    created_at: datetime
    last_opened_at: datetime

from pydantic import BaseModel, ConfigDict

from backend.app.domain.health import HealthStatus


class HealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: HealthStatus
    version: str

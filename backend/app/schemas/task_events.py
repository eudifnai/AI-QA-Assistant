from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from backend.app.domain.task_events import TaskSnapshot, TaskStatus, TaskType


class TaskSnapshotResponse(BaseModel):
    task_type: TaskType
    task_id: str
    workspace_id: str
    status: TaskStatus
    progress: int
    changed_at: datetime

    @classmethod
    def from_domain(cls, item: TaskSnapshot) -> "TaskSnapshotResponse":
        return cls(**{field: getattr(item, field) for field in cls.model_fields})


class TaskStreamEventResponse(BaseModel):
    protocol_version: Literal[1] = 1
    stream_id: str
    sequence: int
    kind: Literal["stream_ready", "task_updated"]
    task: TaskSnapshotResponse | None

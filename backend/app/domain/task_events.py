from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TaskType = Literal[
    "document_parse",
    "analysis",
    "http_execution",
    "websocket_execution",
    "protobuf_execution",
]
TaskStatus = Literal[
    "pending", "queued", "running", "passed", "failed", "error", "cancelled", "timeout"
]
TASK_TYPES: frozenset[str] = frozenset(
    {
        "document_parse",
        "analysis",
        "http_execution",
        "websocket_execution",
        "protobuf_execution",
    }
)
TASK_STATUSES: frozenset[str] = frozenset(
    {"pending", "queued", "running", "passed", "failed", "error", "cancelled", "timeout"}
)


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task_type: TaskType
    task_id: str
    workspace_id: str
    status: TaskStatus
    progress: int
    changed_at: datetime

    def validate(self) -> TaskSnapshot:
        if (
            self.task_type not in TASK_TYPES
            or not self.task_id
            or len(self.task_id) > 128
            or not self.workspace_id
            or len(self.workspace_id) > 128
            or self.status not in TASK_STATUSES
            or not 0 <= self.progress <= 100
            or self.changed_at.tzinfo is None
        ):
            raise ValueError("invalid task snapshot")
        return self

    @property
    def key(self) -> tuple[TaskType, str]:
        return self.task_type, self.task_id

    @property
    def fingerprint(self) -> tuple[TaskStatus, int, datetime]:
        return self.status, self.progress, self.changed_at

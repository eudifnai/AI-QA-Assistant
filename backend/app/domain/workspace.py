from dataclasses import dataclass
from datetime import datetime

MAX_WORKSPACE_NAME_LENGTH = 80


def normalize_workspace_name(name: str) -> str:
    normalized = name.strip()
    if not normalized or len(normalized) > MAX_WORKSPACE_NAME_LENGTH:
        raise ValueError("workspace name must contain between 1 and 80 characters")
    return normalized


@dataclass(frozen=True, slots=True)
class Workspace:
    id: str
    name: str
    path: str
    created_at: datetime
    last_opened_at: datetime


class WorkspaceConflictError(Exception):
    def __init__(self, field: str) -> None:
        super().__init__(f"workspace {field} conflicts with an existing record")
        self.field = field

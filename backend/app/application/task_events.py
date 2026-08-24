from typing import Protocol

from backend.app.core.errors import AppError
from backend.app.domain.task_events import TaskSnapshot
from backend.app.domain.workspace import Workspace


class WorkspaceReader(Protocol):
    def get(self, workspace_id: str) -> Workspace | None: ...


class TaskSnapshotReader(Protocol):
    def list_snapshots(self, workspace_id: str) -> list[TaskSnapshot]: ...


class TaskEventUseCases(Protocol):
    def list_snapshots(self, workspace_id: str) -> list[TaskSnapshot]: ...


class TaskEventService:
    def __init__(
        self,
        workspaces: WorkspaceReader,
        snapshots: TaskSnapshotReader,
    ) -> None:
        self._workspaces = workspaces
        self._snapshots = snapshots

    def list_snapshots(self, workspace_id: str) -> list[TaskSnapshot]:
        if self._workspaces.get(workspace_id) is None:
            raise AppError(
                code="WORKSPACE_NOT_FOUND",
                message="未找到该工作空间。",
                status_code=404,
            )
        items = self._snapshots.list_snapshots(workspace_id)
        seen: set[tuple[object, str]] = set()
        for item in items:
            try:
                item.validate()
            except ValueError as exception:
                raise RuntimeError("task snapshot contract invalid") from exception
            if item.workspace_id != workspace_id or item.key in seen:
                raise RuntimeError("task snapshot contract invalid")
            seen.add(item.key)
        return sorted(items, key=lambda item: item.key)

from datetime import UTC, datetime

import pytest

from backend.app.application.task_events import TaskEventService
from backend.app.core.errors import AppError
from backend.app.domain.task_events import TaskSnapshot
from backend.app.domain.workspace import Workspace

NOW = datetime(2026, 8, 16, 6, 0, tzinfo=UTC)


class Workspaces:
    def get(self, workspace_id: str) -> Workspace | None:
        if workspace_id != "workspace-1":
            return None
        return Workspace("workspace-1", "支付", "E:/qa", NOW, NOW)


class Snapshots:
    def __init__(self, items: list[TaskSnapshot]) -> None:
        self.items = items
        self.workspace_ids: list[str] = []

    def list_snapshots(self, workspace_id: str) -> list[TaskSnapshot]:
        self.workspace_ids.append(workspace_id)
        return self.items


def snapshot(task_type: str, task_id: str, *, workspace_id: str = "workspace-1") -> TaskSnapshot:
    return TaskSnapshot(
        task_type=task_type,  # type: ignore[arg-type]
        task_id=task_id,
        workspace_id=workspace_id,
        status="running",
        progress=35,
        changed_at=NOW,
    )


def test_service_returns_deterministic_workspace_scoped_snapshots() -> None:
    reader = Snapshots([snapshot("websocket_execution", "run-2"), snapshot("analysis", "run-1")])
    service = TaskEventService(Workspaces(), reader)

    result = service.list_snapshots("workspace-1")

    assert [(item.task_type, item.task_id) for item in result] == [
        ("analysis", "run-1"),
        ("websocket_execution", "run-2"),
    ]
    assert reader.workspace_ids == ["workspace-1"]


def test_service_rejects_unknown_workspace_before_reading_tasks() -> None:
    reader = Snapshots([])
    service = TaskEventService(Workspaces(), reader)

    with pytest.raises(AppError) as raised:
        service.list_snapshots("missing")

    assert raised.value.code == "WORKSPACE_NOT_FOUND"
    assert reader.workspace_ids == []


@pytest.mark.parametrize(
    "items",
    [
        [snapshot("analysis", "run-1", workspace_id="workspace-2")],
        [snapshot("analysis", "run-1"), snapshot("analysis", "run-1")],
    ],
)
def test_service_rejects_reader_scope_or_duplicate_contract(items: list[TaskSnapshot]) -> None:
    service = TaskEventService(Workspaces(), Snapshots(items))

    with pytest.raises(RuntimeError, match="task snapshot contract"):
        service.list_snapshots("workspace-1")

from datetime import UTC, datetime

import pytest

from backend.app.domain.task_events import TaskSnapshot

NOW = datetime(2026, 8, 16, 6, 0, tzinfo=UTC)


def test_task_snapshot_validates_safe_progress_contract() -> None:
    snapshot = TaskSnapshot(
        task_type="analysis",
        task_id="run-1",
        workspace_id="workspace-1",
        status="running",
        progress=35,
        changed_at=NOW,
    ).validate()

    assert snapshot.key == ("analysis", "run-1")
    assert snapshot.fingerprint == ("running", 35, NOW)


@pytest.mark.parametrize(
    ("task_id", "workspace_id", "status", "progress"),
    [
        ("", "workspace-1", "running", 10),
        ("run-1", "", "running", 10),
        ("run-1", "workspace-1", "unknown", 10),
        ("run-1", "workspace-1", "running", -1),
        ("run-1", "workspace-1", "running", 101),
    ],
)
def test_task_snapshot_rejects_invalid_contract(
    task_id: str, workspace_id: str, status: str, progress: int
) -> None:
    with pytest.raises(ValueError):
        TaskSnapshot(
            task_type="document_parse",
            task_id=task_id,
            workspace_id=workspace_id,
            status=status,  # type: ignore[arg-type]
            progress=progress,
            changed_at=NOW,
        ).validate()

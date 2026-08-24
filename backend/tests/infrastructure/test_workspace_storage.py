from pathlib import Path

import pytest

from backend.app.core.errors import AppError
from backend.app.infrastructure.workspace_storage import LocalWorkspaceStorage


def test_prepare_requires_an_absolute_path() -> None:
    storage = LocalWorkspaceStorage()

    with pytest.raises(AppError) as raised:
        storage.prepare("relative/workspace")

    assert raised.value.code == "WORKSPACE_PATH_INVALID"


def test_prepare_creates_and_returns_a_resolved_directory(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(minimum_free_bytes=1)
    workspace_path = tmp_path / "new" / "workspace"

    canonical_path = storage.prepare(str(workspace_path))

    assert canonical_path == str(workspace_path.resolve())
    assert workspace_path.is_dir()


def test_ensure_available_rejects_a_removed_directory(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(minimum_free_bytes=1)
    missing_path = tmp_path / "missing"

    with pytest.raises(AppError) as raised:
        storage.ensure_available(str(missing_path))

    assert raised.value.code == "WORKSPACE_PATH_UNAVAILABLE"
    assert raised.value.status_code == 409

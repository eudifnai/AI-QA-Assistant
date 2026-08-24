from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.application.workspaces import WorkspaceRepository, WorkspaceService
from backend.app.core.errors import AppError
from backend.app.domain.workspace import Workspace


class MemoryWorkspaceRepository(WorkspaceRepository):
    def __init__(self) -> None:
        self.items: dict[str, Workspace] = {}

    def list(self) -> list[Workspace]:
        return sorted(self.items.values(), key=lambda item: item.last_opened_at, reverse=True)

    def get(self, workspace_id: str) -> Workspace | None:
        return self.items.get(workspace_id)

    def find_by_name_key(self, name_key: str) -> Workspace | None:
        return next(
            (item for item in self.items.values() if item.name.casefold() == name_key),
            None,
        )

    def find_by_path_key(self, path_key: str) -> Workspace | None:
        return next(
            (item for item in self.items.values() if item.path.casefold() == path_key),
            None,
        )

    def add(self, workspace: Workspace) -> Workspace:
        self.items[workspace.id] = workspace
        return workspace

    def update_last_opened(self, workspace_id: str, opened_at: datetime) -> Workspace:
        previous = self.items[workspace_id]
        updated = Workspace(
            id=previous.id,
            name=previous.name,
            path=previous.path,
            created_at=previous.created_at,
            last_opened_at=opened_at,
        )
        self.items[workspace_id] = updated
        return updated

    def update_name(self, workspace_id: str, name: str) -> Workspace:
        previous = self.items[workspace_id]
        updated = Workspace(
            id=previous.id,
            name=name,
            path=previous.path,
            created_at=previous.created_at,
            last_opened_at=previous.last_opened_at,
        )
        self.items[workspace_id] = updated
        return updated

    def delete(self, workspace_id: str) -> Workspace:
        return self.items.pop(workspace_id)


class StubWorkspaceStorage:
    def __init__(self, canonical_path: str) -> None:
        self.canonical_path = canonical_path
        self.prepared_paths: list[str] = []
        self.checked_paths: list[str] = []

    def prepare(self, path: str) -> str:
        self.prepared_paths.append(path)
        return self.canonical_path

    def ensure_available(self, path: str) -> None:
        self.checked_paths.append(path)


def fixed_clock() -> datetime:
    return datetime(2026, 8, 4, 1, 2, 3, tzinfo=UTC)


def sequence_id_factory() -> Callable[[], str]:
    identifiers = iter(["workspace-1", "workspace-2"])
    return lambda: next(identifiers)


def test_create_workspace_normalizes_name_and_persists_canonical_path(tmp_path: Path) -> None:
    repository = MemoryWorkspaceRepository()
    storage = StubWorkspaceStorage(str(tmp_path / "workspace"))
    service = WorkspaceService(
        repository=repository,
        storage=storage,
        clock=fixed_clock,
        id_factory=sequence_id_factory(),
    )

    workspace = service.create(name="  订单测试  ", path=str(tmp_path / "raw"))

    assert workspace == Workspace(
        id="workspace-1",
        name="订单测试",
        path=str(tmp_path / "workspace"),
        created_at=fixed_clock(),
        last_opened_at=fixed_clock(),
    )
    assert repository.list() == [workspace]


def test_create_workspace_rejects_duplicate_name_case_insensitively(tmp_path: Path) -> None:
    repository = MemoryWorkspaceRepository()
    storage = StubWorkspaceStorage(str(tmp_path / "first"))
    service = WorkspaceService(repository=repository, storage=storage)
    service.create(name="Demo", path=str(tmp_path / "first"))
    storage.canonical_path = str(tmp_path / "second")

    with pytest.raises(AppError) as raised:
        service.create(name="demo", path=str(tmp_path / "second"))

    assert raised.value.code == "WORKSPACE_NAME_CONFLICT"
    assert raised.value.status_code == 409


def test_open_workspace_checks_path_and_updates_recent_order(tmp_path: Path) -> None:
    repository = MemoryWorkspaceRepository()
    storage = StubWorkspaceStorage(str(tmp_path / "workspace"))
    first_time = datetime(2026, 8, 4, 1, 0, tzinfo=UTC)
    second_time = datetime(2026, 8, 4, 2, 0, tzinfo=UTC)
    times = iter([first_time, second_time])
    service = WorkspaceService(
        repository=repository,
        storage=storage,
        clock=lambda: next(times),
        id_factory=lambda: "workspace-1",
    )
    created = service.create(name="Demo", path=str(tmp_path / "workspace"))

    opened = service.open(created.id)

    assert storage.checked_paths == [created.path]
    assert opened.last_opened_at == second_time


def test_open_workspace_reports_missing_record() -> None:
    service = WorkspaceService(
        repository=MemoryWorkspaceRepository(),
        storage=StubWorkspaceStorage("C:\\workspace"),
    )

    with pytest.raises(AppError) as raised:
        service.open("missing")

    assert raised.value.code == "WORKSPACE_NOT_FOUND"
    assert raised.value.status_code == 404


def test_rename_workspace_normalizes_name_without_changing_path(tmp_path: Path) -> None:
    repository = MemoryWorkspaceRepository()
    storage = StubWorkspaceStorage(str(tmp_path / "workspace"))
    service = WorkspaceService(
        repository=repository,
        storage=storage,
        clock=fixed_clock,
        id_factory=lambda: "workspace-1",
    )
    created = service.create(name="旧名称", path=str(tmp_path / "workspace"))

    renamed = service.rename(created.id, "  新名称  ")

    assert renamed.name == "新名称"
    assert renamed.path == created.path
    assert renamed.created_at == created.created_at
    assert renamed.last_opened_at == created.last_opened_at


def test_rename_workspace_rejects_duplicate_name_case_insensitively(tmp_path: Path) -> None:
    repository = MemoryWorkspaceRepository()
    storage = StubWorkspaceStorage(str(tmp_path / "first"))
    service = WorkspaceService(repository=repository, storage=storage)
    first = service.create(name="First", path=str(tmp_path / "first"))
    storage.canonical_path = str(tmp_path / "second")
    second = service.create(name="Second", path=str(tmp_path / "second"))

    with pytest.raises(AppError) as raised:
        service.rename(second.id, "first")

    assert raised.value.code == "WORKSPACE_NAME_CONFLICT"
    assert repository.get(first.id) == first
    assert repository.get(second.id) == second


def test_rename_workspace_allows_case_change_for_same_record(tmp_path: Path) -> None:
    repository = MemoryWorkspaceRepository()
    storage = StubWorkspaceStorage(str(tmp_path / "workspace"))
    service = WorkspaceService(repository=repository, storage=storage)
    created = service.create(name="Demo", path=str(tmp_path / "workspace"))

    renamed = service.rename(created.id, "DEMO")

    assert renamed.name == "DEMO"


@pytest.mark.parametrize("operation", ["rename", "delete"])
def test_workspace_mutation_reports_missing_record(operation: str) -> None:
    service = WorkspaceService(
        repository=MemoryWorkspaceRepository(),
        storage=StubWorkspaceStorage("C:\\workspace"),
    )

    with pytest.raises(AppError) as raised:
        if operation == "rename":
            service.rename("missing", "新名称")
        else:
            service.delete("missing")

    assert raised.value.code == "WORKSPACE_NOT_FOUND"
    assert raised.value.status_code == 404


def test_delete_workspace_removes_only_repository_record(tmp_path: Path) -> None:
    repository = MemoryWorkspaceRepository()
    storage = StubWorkspaceStorage(str(tmp_path / "workspace"))
    service = WorkspaceService(repository=repository, storage=storage)
    created = service.create(name="Demo", path=str(tmp_path / "workspace"))

    deleted = service.delete(created.id)

    assert deleted == created
    assert repository.list() == []
    assert storage.checked_paths == []

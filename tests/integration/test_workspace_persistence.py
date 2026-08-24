from pathlib import Path

from alembic import command

from backend.app.application.workspaces import WorkspaceService
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.workspace_storage import LocalWorkspaceStorage
from backend.app.infrastructure.workspaces import SqlModelWorkspaceRepository
from tests.integration.test_migrations import migration_config


def test_workspace_is_recovered_by_a_new_service_instance(tmp_path: Path) -> None:
    database_path = tmp_path / "workspace.db"
    command.upgrade(migration_config(database_path), "head")
    engine = create_database_engine(f"sqlite:///{database_path.as_posix()}")
    workspace_path = tmp_path / "project-files"

    first_service = WorkspaceService(
        repository=SqlModelWorkspaceRepository(engine),
        storage=LocalWorkspaceStorage(minimum_free_bytes=1),
    )
    created = first_service.create(name="持久化项目", path=str(workspace_path))

    restarted_service = WorkspaceService(
        repository=SqlModelWorkspaceRepository(engine),
        storage=LocalWorkspaceStorage(minimum_free_bytes=1),
    )

    assert restarted_service.list() == [created]


def test_workspace_rename_and_record_deletion_survive_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "workspace.db"
    command.upgrade(migration_config(database_path), "head")
    engine = create_database_engine(f"sqlite:///{database_path.as_posix()}")
    workspace_path = tmp_path / "project-files"
    service = WorkspaceService(
        repository=SqlModelWorkspaceRepository(engine),
        storage=LocalWorkspaceStorage(minimum_free_bytes=1),
    )
    created = service.create(name="旧名称", path=str(workspace_path))

    renamed = service.rename(created.id, "新名称")

    restarted_service = WorkspaceService(
        repository=SqlModelWorkspaceRepository(engine),
        storage=LocalWorkspaceStorage(minimum_free_bytes=1),
    )
    assert restarted_service.list() == [renamed]

    deleted = restarted_service.delete(created.id)

    final_service = WorkspaceService(
        repository=SqlModelWorkspaceRepository(engine),
        storage=LocalWorkspaceStorage(minimum_free_bytes=1),
    )
    assert deleted == renamed
    assert final_service.list() == []
    assert workspace_path.is_dir()

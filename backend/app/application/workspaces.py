from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from backend.app.core.errors import AppError
from backend.app.domain.workspace import (
    Workspace,
    WorkspaceConflictError,
    normalize_workspace_name,
)


class WorkspaceRepository(Protocol):
    def list(self) -> list[Workspace]: ...

    def get(self, workspace_id: str) -> Workspace | None: ...

    def find_by_name_key(self, name_key: str) -> Workspace | None: ...

    def find_by_path_key(self, path_key: str) -> Workspace | None: ...

    def add(self, workspace: Workspace) -> Workspace: ...

    def update_last_opened(self, workspace_id: str, opened_at: datetime) -> Workspace: ...

    def update_name(self, workspace_id: str, name: str) -> Workspace: ...

    def delete(self, workspace_id: str) -> Workspace: ...


class WorkspaceStorage(Protocol):
    def prepare(self, path: str) -> str: ...

    def ensure_available(self, path: str) -> None: ...


class WorkspaceUseCases(Protocol):
    def list(self) -> list[Workspace]: ...

    def create(self, *, name: str, path: str) -> Workspace: ...

    def open(self, workspace_id: str) -> Workspace: ...

    def rename(self, workspace_id: str, name: str) -> Workspace: ...

    def delete(self, workspace_id: str) -> Workspace: ...


class WorkspaceService:
    def __init__(
        self,
        repository: WorkspaceRepository,
        storage: WorkspaceStorage,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def list(self) -> list[Workspace]:
        return self._repository.list()

    def create(self, *, name: str, path: str) -> Workspace:
        normalized_name = normalize_workspace_name(name)
        if self._repository.find_by_name_key(normalized_name.casefold()) is not None:
            raise AppError(
                code="WORKSPACE_NAME_CONFLICT",
                message="工作空间名称已存在。",
                status_code=409,
            )

        canonical_path = self._storage.prepare(path)
        if self._repository.find_by_path_key(canonical_path.casefold()) is not None:
            raise AppError(
                code="WORKSPACE_PATH_CONFLICT",
                message="该目录已关联其他工作空间。",
                status_code=409,
            )

        now = self._clock()
        workspace = Workspace(
            id=self._id_factory(),
            name=normalized_name,
            path=canonical_path,
            created_at=now,
            last_opened_at=now,
        )
        try:
            return self._repository.add(workspace)
        except WorkspaceConflictError as exception:
            if exception.field == "name":
                raise AppError(
                    code="WORKSPACE_NAME_CONFLICT",
                    message="工作空间名称已存在。",
                    status_code=409,
                ) from exception
            raise AppError(
                code="WORKSPACE_PATH_CONFLICT",
                message="该目录已关联其他工作空间。",
                status_code=409,
            ) from exception

    def open(self, workspace_id: str) -> Workspace:
        workspace = self._get_required(workspace_id)
        self._storage.ensure_available(workspace.path)
        return self._repository.update_last_opened(workspace.id, self._clock())

    def rename(self, workspace_id: str, name: str) -> Workspace:
        workspace = self._get_required(workspace_id)
        normalized_name = normalize_workspace_name(name)
        conflict = self._repository.find_by_name_key(normalized_name.casefold())
        if conflict is not None and conflict.id != workspace.id:
            raise AppError(
                code="WORKSPACE_NAME_CONFLICT",
                message="工作空间名称已存在。",
                status_code=409,
            )
        try:
            return self._repository.update_name(workspace.id, normalized_name)
        except WorkspaceConflictError as exception:
            raise AppError(
                code="WORKSPACE_NAME_CONFLICT",
                message="工作空间名称已存在。",
                status_code=409,
            ) from exception
        except LookupError as exception:
            raise self._not_found_error() from exception

    def delete(self, workspace_id: str) -> Workspace:
        workspace = self._get_required(workspace_id)
        try:
            return self._repository.delete(workspace.id)
        except LookupError as exception:
            raise self._not_found_error() from exception

    def _get_required(self, workspace_id: str) -> Workspace:
        workspace = self._repository.get(workspace_id)
        if workspace is None:
            raise self._not_found_error()
        return workspace

    @staticmethod
    def _not_found_error() -> AppError:
        return AppError(
            code="WORKSPACE_NOT_FOUND",
            message="未找到该工作空间。",
            status_code=404,
        )

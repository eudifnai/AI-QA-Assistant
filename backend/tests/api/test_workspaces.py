from datetime import UTC, datetime
from typing import NoReturn

from fastapi.testclient import TestClient

from backend.app.core.errors import AppError
from backend.app.domain.workspace import Workspace
from backend.app.main import create_app

WORKSPACE = Workspace(
    id="987f5b57-7f20-47c9-b45c-b011653368f1",
    name="支付项目",
    path="C:\\qa\\payment",
    created_at=datetime(2026, 8, 4, 1, 0, tzinfo=UTC),
    last_opened_at=datetime(2026, 8, 4, 2, 0, tzinfo=UTC),
)


class StubWorkspaceService:
    def __init__(self) -> None:
        self.created_with: tuple[str, str] | None = None
        self.opened_id: str | None = None
        self.renamed_with: tuple[str, str] | None = None
        self.deleted_id: str | None = None

    def list(self) -> list[Workspace]:
        return [WORKSPACE]

    def create(self, *, name: str, path: str) -> Workspace:
        self.created_with = (name, path)
        return WORKSPACE

    def open(self, workspace_id: str) -> Workspace:
        self.opened_id = workspace_id
        return WORKSPACE

    def rename(self, workspace_id: str, name: str) -> Workspace:
        self.renamed_with = (workspace_id, name)
        return WORKSPACE

    def delete(self, workspace_id: str) -> Workspace:
        self.deleted_id = workspace_id
        return WORKSPACE


class FailingWorkspaceService(StubWorkspaceService):
    def create(self, *, name: str, path: str) -> NoReturn:
        raise AppError(
            code="WORKSPACE_NAME_CONFLICT",
            message="工作空间名称已存在。",
            status_code=409,
        )


class CrashingWorkspaceService(StubWorkspaceService):
    def list(self) -> NoReturn:
        raise RuntimeError("sensitive database detail")


class ConflictingRenameWorkspaceService(StubWorkspaceService):
    def rename(self, workspace_id: str, name: str) -> NoReturn:
        raise AppError(
            code="WORKSPACE_NAME_CONFLICT",
            message="工作空间名称已存在。",
            status_code=409,
        )


class MissingDeleteWorkspaceService(StubWorkspaceService):
    def delete(self, workspace_id: str) -> NoReturn:
        raise AppError(
            code="WORKSPACE_NOT_FOUND",
            message="未找到该工作空间。",
            status_code=404,
        )


class CrashingRenameWorkspaceService(StubWorkspaceService):
    def rename(self, workspace_id: str, name: str) -> NoReturn:
        raise RuntimeError("sensitive rename detail")


def test_list_workspaces_returns_recent_records() -> None:
    app = create_app(workspace_service=StubWorkspaceService())

    with TestClient(app) as client:
        response = client.get("/api/workspaces")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": WORKSPACE.id,
            "name": "支付项目",
            "path": "C:\\qa\\payment",
            "created_at": "2026-08-04T01:00:00Z",
            "last_opened_at": "2026-08-04T02:00:00Z",
        }
    ]


def test_create_workspace_validates_and_delegates() -> None:
    service = StubWorkspaceService()
    app = create_app(workspace_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/api/workspaces",
            json={"name": "支付项目", "path": "C:\\qa\\payment"},
        )

    assert response.status_code == 201
    assert service.created_with == ("支付项目", "C:\\qa\\payment")
    assert response.json()["id"] == WORKSPACE.id


def test_create_workspace_rejects_invalid_payload() -> None:
    app = create_app(workspace_service=StubWorkspaceService())

    with TestClient(app) as client:
        response = client.post("/api/workspaces", json={"name": "", "path": ""})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_create_workspace_rejects_whitespace_name() -> None:
    app = create_app(workspace_service=StubWorkspaceService())

    with TestClient(app) as client:
        response = client.post(
            "/api/workspaces",
            json={"name": "   ", "path": "C:\\qa\\payment"},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_create_workspace_maps_business_failure() -> None:
    app = create_app(workspace_service=FailingWorkspaceService())

    with TestClient(app) as client:
        response = client.post(
            "/api/workspaces",
            json={"name": "支付项目", "path": "C:\\qa\\payment"},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "WORKSPACE_NAME_CONFLICT"


def test_workspace_unexpected_failure_is_redacted() -> None:
    app = create_app(workspace_service=CrashingWorkspaceService())

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/workspaces")

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "sensitive database detail" not in response.text


def test_open_workspace_delegates_by_id() -> None:
    service = StubWorkspaceService()
    app = create_app(workspace_service=service)

    with TestClient(app) as client:
        response = client.post(f"/api/workspaces/{WORKSPACE.id}/open")

    assert response.status_code == 200
    assert service.opened_id == WORKSPACE.id


def test_rename_workspace_validates_and_delegates() -> None:
    service = StubWorkspaceService()
    app = create_app(workspace_service=service)

    with TestClient(app) as client:
        response = client.patch(
            f"/api/workspaces/{WORKSPACE.id}",
            json={"name": "新名称"},
        )

    assert response.status_code == 200
    assert service.renamed_with == (WORKSPACE.id, "新名称")
    assert response.json()["id"] == WORKSPACE.id


def test_rename_workspace_rejects_blank_name() -> None:
    app = create_app(workspace_service=StubWorkspaceService())

    with TestClient(app) as client:
        response = client.patch(
            f"/api/workspaces/{WORKSPACE.id}",
            json={"name": "   "},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_rename_workspace_maps_name_conflict() -> None:
    app = create_app(workspace_service=ConflictingRenameWorkspaceService())

    with TestClient(app) as client:
        response = client.patch(
            f"/api/workspaces/{WORKSPACE.id}",
            json={"name": "重复名称"},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "WORKSPACE_NAME_CONFLICT"


def test_rename_workspace_unexpected_failure_is_redacted() -> None:
    app = create_app(workspace_service=CrashingRenameWorkspaceService())

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.patch(
            f"/api/workspaces/{WORKSPACE.id}",
            json={"name": "新名称"},
        )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "sensitive rename detail" not in response.text


def test_delete_workspace_delegates_by_id() -> None:
    service = StubWorkspaceService()
    app = create_app(workspace_service=service)

    with TestClient(app) as client:
        response = client.delete(f"/api/workspaces/{WORKSPACE.id}")

    assert response.status_code == 200
    assert service.deleted_id == WORKSPACE.id
    assert response.json()["path"] == WORKSPACE.path


def test_delete_workspace_maps_missing_record() -> None:
    app = create_app(workspace_service=MissingDeleteWorkspaceService())

    with TestClient(app) as client:
        response = client.delete(f"/api/workspaces/{WORKSPACE.id}")

    assert response.status_code == 404
    assert response.json()["code"] == "WORKSPACE_NOT_FOUND"

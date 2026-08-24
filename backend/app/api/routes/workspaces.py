from fastapi import APIRouter, status

from backend.app.application.workspaces import WorkspaceUseCases
from backend.app.schemas.workspaces import (
    WorkspaceCreateRequest,
    WorkspaceNameRequest,
    WorkspaceResponse,
)


def create_workspace_router(service: WorkspaceUseCases) -> APIRouter:
    router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

    @router.get("", response_model=list[WorkspaceResponse])
    def list_workspaces() -> list[WorkspaceResponse]:
        return [WorkspaceResponse.model_validate(item) for item in service.list()]

    @router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
    def create_workspace(payload: WorkspaceCreateRequest) -> WorkspaceResponse:
        workspace = service.create(name=payload.name, path=payload.path)
        return WorkspaceResponse.model_validate(workspace)

    @router.post("/{workspace_id}/open", response_model=WorkspaceResponse)
    def open_workspace(workspace_id: str) -> WorkspaceResponse:
        return WorkspaceResponse.model_validate(service.open(workspace_id))

    @router.patch("/{workspace_id}", response_model=WorkspaceResponse)
    def rename_workspace(workspace_id: str, payload: WorkspaceNameRequest) -> WorkspaceResponse:
        return WorkspaceResponse.model_validate(service.rename(workspace_id, payload.name))

    @router.delete("/{workspace_id}", response_model=WorkspaceResponse)
    def delete_workspace(workspace_id: str) -> WorkspaceResponse:
        return WorkspaceResponse.model_validate(service.delete(workspace_id))

    return router

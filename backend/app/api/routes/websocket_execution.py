from fastapi import APIRouter, status

from backend.app.application.websocket_execution import WebSocketExecutionUseCases
from backend.app.schemas.websocket_execution import (
    WebSocketExecutionResponse,
    WebSocketExecutionStartRequest,
)


def create_websocket_execution_router(service: WebSocketExecutionUseCases) -> APIRouter:
    router = APIRouter(tags=["websocket-execution"])

    @router.post(
        "/api/workspaces/{workspace_id}/websocket-executions",
        response_model=WebSocketExecutionResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def start_execution(
        workspace_id: str, request: WebSocketExecutionStartRequest
    ) -> WebSocketExecutionResponse:
        return WebSocketExecutionResponse.from_domain(
            service.start(workspace_id, request.to_input())
        )

    @router.get(
        "/api/workspaces/{workspace_id}/websocket-executions",
        response_model=list[WebSocketExecutionResponse],
    )
    def list_executions(workspace_id: str) -> list[WebSocketExecutionResponse]:
        return [
            WebSocketExecutionResponse.from_domain(item) for item in service.list_runs(workspace_id)
        ]

    @router.get(
        "/api/workspaces/{workspace_id}/websocket-executions/{run_id}",
        response_model=WebSocketExecutionResponse,
    )
    def get_execution(workspace_id: str, run_id: str) -> WebSocketExecutionResponse:
        return WebSocketExecutionResponse.from_domain(service.get_run(workspace_id, run_id))

    @router.post(
        "/api/workspaces/{workspace_id}/websocket-executions/{run_id}/cancel",
        response_model=WebSocketExecutionResponse,
    )
    def cancel_execution(workspace_id: str, run_id: str) -> WebSocketExecutionResponse:
        return WebSocketExecutionResponse.from_domain(service.cancel(workspace_id, run_id))

    return router

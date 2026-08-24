from fastapi import APIRouter, status

from backend.app.application.protobuf_execution import ProtoExecutionUseCases
from backend.app.schemas.protobuf_execution import (
    ProtoExecutionResponse,
    ProtoExecutionStartRequest,
)


def create_protobuf_execution_router(service: ProtoExecutionUseCases) -> APIRouter:
    router = APIRouter(tags=["protobuf-execution"])

    @router.post(
        "/api/workspaces/{workspace_id}/protobuf-executions",
        response_model=ProtoExecutionResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def start_execution(
        workspace_id: str, request: ProtoExecutionStartRequest
    ) -> ProtoExecutionResponse:
        return ProtoExecutionResponse.from_domain(service.start(workspace_id, request.to_input()))

    @router.get(
        "/api/workspaces/{workspace_id}/protobuf-executions",
        response_model=list[ProtoExecutionResponse],
    )
    def list_executions(workspace_id: str) -> list[ProtoExecutionResponse]:
        return [
            ProtoExecutionResponse.from_domain(item) for item in service.list_runs(workspace_id)
        ]

    @router.get(
        "/api/workspaces/{workspace_id}/protobuf-executions/{run_id}",
        response_model=ProtoExecutionResponse,
    )
    def get_execution(workspace_id: str, run_id: str) -> ProtoExecutionResponse:
        return ProtoExecutionResponse.from_domain(service.get_run(workspace_id, run_id))

    @router.post(
        "/api/workspaces/{workspace_id}/protobuf-executions/{run_id}/cancel",
        response_model=ProtoExecutionResponse,
    )
    def cancel_execution(workspace_id: str, run_id: str) -> ProtoExecutionResponse:
        return ProtoExecutionResponse.from_domain(service.cancel(workspace_id, run_id))

    return router

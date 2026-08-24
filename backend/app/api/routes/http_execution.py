from fastapi import APIRouter, Response, status

from backend.app.application.http_execution import HttpExecutionUseCases
from backend.app.schemas.http_execution import (
    HttpEnvironmentRequest,
    HttpEnvironmentResponse,
    HttpExecutionResponse,
    HttpExecutionStartRequest,
    HttpSecretRequest,
)


def create_http_execution_router(service: HttpExecutionUseCases) -> APIRouter:
    router = APIRouter(tags=["http-execution"])

    @router.get(
        "/api/workspaces/{workspace_id}/http-environments",
        response_model=list[HttpEnvironmentResponse],
    )
    def list_environments(workspace_id: str) -> list[HttpEnvironmentResponse]:
        return [
            HttpEnvironmentResponse.from_domain(item)
            for item in service.list_environments(workspace_id)
        ]

    @router.post(
        "/api/workspaces/{workspace_id}/http-environments",
        response_model=HttpEnvironmentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_environment(
        workspace_id: str, request: HttpEnvironmentRequest
    ) -> HttpEnvironmentResponse:
        return HttpEnvironmentResponse.from_domain(
            service.create_environment(workspace_id, request.to_input())
        )

    @router.put(
        "/api/workspaces/{workspace_id}/http-environments/{environment_id}",
        response_model=HttpEnvironmentResponse,
    )
    def update_environment(
        workspace_id: str,
        environment_id: str,
        request: HttpEnvironmentRequest,
    ) -> HttpEnvironmentResponse:
        return HttpEnvironmentResponse.from_domain(
            service.update_environment(workspace_id, environment_id, request.to_input())
        )

    @router.delete(
        "/api/workspaces/{workspace_id}/http-environments/{environment_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_environment(workspace_id: str, environment_id: str) -> Response:
        service.delete_environment(workspace_id, environment_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.put(
        "/api/workspaces/{workspace_id}/http-environments/{environment_id}/secrets/{name}",
        response_model=HttpEnvironmentResponse,
    )
    def set_secret(
        workspace_id: str,
        environment_id: str,
        name: str,
        request: HttpSecretRequest,
    ) -> HttpEnvironmentResponse:
        return HttpEnvironmentResponse.from_domain(
            service.set_secret(workspace_id, environment_id, name, request.secret)
        )

    @router.delete(
        "/api/workspaces/{workspace_id}/http-environments/{environment_id}/secrets/{name}",
        response_model=HttpEnvironmentResponse,
    )
    def delete_secret(workspace_id: str, environment_id: str, name: str) -> HttpEnvironmentResponse:
        return HttpEnvironmentResponse.from_domain(
            service.delete_secret(workspace_id, environment_id, name)
        )

    @router.post(
        "/api/workspaces/{workspace_id}/http-executions",
        response_model=HttpExecutionResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def start_execution(
        workspace_id: str, request: HttpExecutionStartRequest
    ) -> HttpExecutionResponse:
        return HttpExecutionResponse.from_domain(service.start(workspace_id, request.to_input()))

    @router.get(
        "/api/workspaces/{workspace_id}/http-executions",
        response_model=list[HttpExecutionResponse],
    )
    def list_executions(workspace_id: str) -> list[HttpExecutionResponse]:
        return [HttpExecutionResponse.from_domain(item) for item in service.list_runs(workspace_id)]

    @router.get(
        "/api/workspaces/{workspace_id}/http-executions/{run_id}",
        response_model=HttpExecutionResponse,
    )
    def get_execution(workspace_id: str, run_id: str) -> HttpExecutionResponse:
        return HttpExecutionResponse.from_domain(service.get_run(workspace_id, run_id))

    @router.post(
        "/api/workspaces/{workspace_id}/http-executions/{run_id}/cancel",
        response_model=HttpExecutionResponse,
    )
    def cancel_execution(workspace_id: str, run_id: str) -> HttpExecutionResponse:
        return HttpExecutionResponse.from_domain(service.cancel(workspace_id, run_id))

    @router.post(
        "/api/workspaces/{workspace_id}/http-executions/{run_id}/rerun",
        response_model=HttpExecutionResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def rerun_execution(workspace_id: str, run_id: str) -> HttpExecutionResponse:
        return HttpExecutionResponse.from_domain(service.rerun(workspace_id, run_id))

    return router

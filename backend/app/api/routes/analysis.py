from fastapi import APIRouter, status

from backend.app.application.analysis import AnalysisUseCases
from backend.app.schemas.analysis import AnalysisRunResponse, AnalysisStartRequest


def create_analysis_router(service: AnalysisUseCases) -> APIRouter:
    router = APIRouter(tags=["analysis"])

    @router.post(
        "/api/workspaces/{workspace_id}/documents/{document_id}/analysis-runs",
        response_model=AnalysisRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def start_analysis(
        workspace_id: str,
        document_id: str,
        request: AnalysisStartRequest,
    ) -> AnalysisRunResponse:
        return AnalysisRunResponse.from_domain(
            service.start(workspace_id, document_id, request.to_input())
        )

    @router.get(
        "/api/workspaces/{workspace_id}/documents/{document_id}/analysis-runs",
        response_model=list[AnalysisRunResponse],
    )
    def list_analysis_runs(workspace_id: str, document_id: str) -> list[AnalysisRunResponse]:
        return [
            AnalysisRunResponse.from_domain(run)
            for run in service.list_runs(workspace_id, document_id)
        ]

    @router.get(
        "/api/workspaces/{workspace_id}/analysis-runs/{run_id}",
        response_model=AnalysisRunResponse,
    )
    def get_analysis_run(workspace_id: str, run_id: str) -> AnalysisRunResponse:
        return AnalysisRunResponse.from_domain(service.get_run(workspace_id, run_id))

    @router.post(
        "/api/workspaces/{workspace_id}/analysis-runs/{run_id}/cancel",
        response_model=AnalysisRunResponse,
    )
    def cancel_analysis_run(workspace_id: str, run_id: str) -> AnalysisRunResponse:
        return AnalysisRunResponse.from_domain(service.cancel(workspace_id, run_id))

    return router

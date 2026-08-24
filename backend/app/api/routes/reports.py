from fastapi import APIRouter

from backend.app.application.reports import ReportUseCases
from backend.app.schemas.reports import (
    ReportArtifactResponse,
    ReportRenderRequest,
    ReportSnapshotResponse,
)


def create_report_router(service: ReportUseCases) -> APIRouter:
    router = APIRouter(prefix="/api/workspaces/{workspace_id}/report", tags=["reports"])

    @router.get("", response_model=ReportSnapshotResponse)
    def get_report(workspace_id: str) -> ReportSnapshotResponse:
        return ReportSnapshotResponse.from_domain(service.get_snapshot(workspace_id))

    @router.post("/render", response_model=ReportArtifactResponse)
    def render_report(workspace_id: str, request: ReportRenderRequest) -> ReportArtifactResponse:
        return ReportArtifactResponse.from_domain(service.render(workspace_id, request.format))

    return router

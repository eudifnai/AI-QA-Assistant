from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from backend.app.core.errors import AppError
from backend.app.domain.reports import (
    ReportArtifact,
    ReportData,
    ReportFormat,
    ReportSnapshot,
    build_report_snapshot,
)
from backend.app.domain.workspace import Workspace


class WorkspaceReader(Protocol):
    def get(self, workspace_id: str) -> Workspace | None: ...


class ReportReader(Protocol):
    def read(self, workspace_id: str) -> ReportData: ...


class ReportRenderer(Protocol):
    def render(self, snapshot: ReportSnapshot, format_name: ReportFormat) -> ReportArtifact: ...


class ReportUseCases(Protocol):
    def get_snapshot(self, workspace_id: str) -> ReportSnapshot: ...

    def render(self, workspace_id: str, format_name: ReportFormat) -> ReportArtifact: ...


class ReportService:
    def __init__(
        self,
        workspaces: WorkspaceReader,
        reader: ReportReader,
        renderer: ReportRenderer,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._workspaces = workspaces
        self._reader = reader
        self._renderer = renderer
        self._clock = clock

    def get_snapshot(self, workspace_id: str) -> ReportSnapshot:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise AppError(
                code="WORKSPACE_NOT_FOUND",
                message="工作空间不存在。",
                status_code=404,
            )
        data = self._reader.read(workspace_id)
        return build_report_snapshot(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            generated_at=self._clock(),
            executions=data.executions,
            analysis_summary=data.analysis_summary,
            design_summary=data.design_summary,
        )

    def render(self, workspace_id: str, format_name: ReportFormat) -> ReportArtifact:
        snapshot = self.get_snapshot(workspace_id)
        try:
            return self._renderer.render(snapshot, format_name)
        except ValueError as exception:
            raise AppError(
                code="REPORT_FORMAT_UNSUPPORTED",
                message="不支持该报告格式。",
                status_code=422,
            ) from exception

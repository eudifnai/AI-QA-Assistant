from datetime import UTC, datetime

import pytest

from backend.app.application.reports import ReportService
from backend.app.core.errors import AppError
from backend.app.domain.reports import (
    ReportAnalysisSummary,
    ReportArtifact,
    ReportData,
    ReportDesignSummary,
    ReportFormat,
    ReportSnapshot,
)
from backend.app.domain.workspace import Workspace

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


class Workspaces:
    def get(self, workspace_id: str) -> Workspace | None:
        if workspace_id != "workspace-1":
            return None
        return Workspace("workspace-1", "支付项目", "C:/qa/pay", NOW, NOW)


class Reader:
    workspace_id: str | None = None

    def read(self, workspace_id: str) -> ReportData:
        self.workspace_id = workspace_id
        return ReportData(
            (),
            ReportAnalysisSummary(0, 0, 0, None, 0),
            ReportDesignSummary(0, 0, 0, 0),
        )


class Renderer:
    def render(self, snapshot: ReportSnapshot, format_name: ReportFormat) -> ReportArtifact:
        return ReportArtifact(format_name, f"report.{format_name}", "text/plain", "content", NOW)


def test_report_service_scopes_snapshot_and_render_to_workspace() -> None:
    reader = Reader()
    service = ReportService(Workspaces(), reader, Renderer(), clock=lambda: NOW)

    snapshot = service.get_snapshot("workspace-1")
    artifact = service.render("workspace-1", "markdown")

    assert snapshot.workspace_id == "workspace-1"
    assert snapshot.workspace_name == "支付项目"
    assert reader.workspace_id == "workspace-1"
    assert artifact.format == "markdown"


def test_report_service_rejects_missing_workspace_before_reading() -> None:
    reader = Reader()
    service = ReportService(Workspaces(), reader, Renderer(), clock=lambda: NOW)

    with pytest.raises(AppError) as captured:
        service.get_snapshot("missing")

    assert captured.value.code == "WORKSPACE_NOT_FOUND"
    assert reader.workspace_id is None

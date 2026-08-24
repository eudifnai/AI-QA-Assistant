from datetime import UTC, datetime
from typing import NoReturn

from fastapi.testclient import TestClient

from backend.app.application.reports import ReportUseCases
from backend.app.domain.reports import (
    ReportAnalysisSummary,
    ReportArtifact,
    ReportDesignSummary,
    ReportFormat,
    ReportSnapshot,
    build_report_snapshot,
)
from backend.app.main import create_app

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
SNAPSHOT = build_report_snapshot(
    workspace_id="workspace-1",
    workspace_name="支付项目",
    generated_at=NOW,
    executions=(),
    analysis_summary=ReportAnalysisSummary(0, 0, 0, None, 0),
    design_summary=ReportDesignSummary(0, 0, 0, 0),
)


class Reports(ReportUseCases):
    workspace_id: str | None = None
    format_name: str | None = None

    def get_snapshot(self, workspace_id: str) -> ReportSnapshot:
        self.workspace_id = workspace_id
        return SNAPSHOT

    def render(self, workspace_id: str, format_name: ReportFormat) -> ReportArtifact:
        self.workspace_id = workspace_id
        self.format_name = format_name
        return ReportArtifact(
            format_name,
            "payment-report.md",
            "text/markdown",
            "# safe report\n",
            NOW,
        )


class CrashingReports(Reports):
    def get_snapshot(self, workspace_id: str) -> NoReturn:
        raise RuntimeError("Authorization: Bearer secret-report-token")


def test_report_api_returns_scoped_snapshot_and_rendered_artifact() -> None:
    service = Reports()
    app = create_app(report_service=service)

    with TestClient(app) as client:
        snapshot = client.get("/api/workspaces/workspace-1/report")
        rendered = client.post(
            "/api/workspaces/workspace-1/report/render", json={"format": "markdown"}
        )

    assert snapshot.status_code == 200
    assert snapshot.json()["workspace_id"] == "workspace-1"
    assert snapshot.json()["schema_version"] == 2
    assert snapshot.json()["execution_summary"]["total"] == 0
    assert snapshot.json()["execution_summary"]["evaluated"] == 0
    assert len(snapshot.json()["trend"]) == 14
    assert snapshot.json()["failure_attribution_summary"]["total"] == 0
    assert rendered.status_code == 200
    assert rendered.json()["file_name"] == "payment-report.md"
    assert rendered.json()["content"] == "# safe report\n"
    assert service.workspace_id == "workspace-1"
    assert service.format_name == "markdown"


def test_report_api_rejects_unknown_format_without_calling_service() -> None:
    service = Reports()
    app = create_app(report_service=service)

    with TestClient(app) as client:
        response = client.post("/api/workspaces/workspace-1/report/render", json={"format": "pdf"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert service.workspace_id is None


def test_report_api_redacts_unexpected_failure() -> None:
    app = create_app(report_service=CrashingReports())

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/workspaces/workspace-1/report")

    assert response.status_code == 500
    assert "secret-report-token" not in response.text

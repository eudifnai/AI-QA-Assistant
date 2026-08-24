from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, SQLModel

from backend.app.infrastructure.analysis import AnalysisIssueRecord, AnalysisRunRecord
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.documents import DocumentRecord, DocumentVersionRecord
from backend.app.infrastructure.http_execution import HttpExecutionEventRecord, HttpExecutionRecord
from backend.app.infrastructure.reports import SqlModelReportReader
from backend.app.infrastructure.test_design import (
    TestCaseRecord as CaseRecord,
)
from backend.app.infrastructure.test_design import (
    TestPointRecord as PointRecord,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def _workspace(identifier: str, root: Path) -> WorkspaceRecord:
    return WorkspaceRecord(
        id=identifier,
        name=identifier,
        name_key=identifier,
        path=str(root / identifier),
        path_key=str(root / identifier).casefold(),
        created_at=NOW,
        last_opened_at=NOW,
    )


def _http_run(identifier: str, workspace_id: str) -> HttpExecutionRecord:
    return HttpExecutionRecord(
        id=identifier,
        workspace_id=workspace_id,
        environment_name="测试环境",
        base_url="https://api.example.test",
        variables_json='{"PUBLIC":"value"}',
        secret_names_json='["API_TOKEN"]',
        method="GET",
        path_template="/health",
        headers_template_json='{"Authorization":"Bearer {{secret.API_TOKEN}}"}',
        body_template="never-export-this-body",
        timeout_seconds=10,
        status="passed",
        progress=100,
        response_status_code=200,
        response_headers_json='{"Set-Cookie":"***"}',
        response_body="never-export-this-response",
        response_body_encoding="text",
        response_size_bytes=2,
        duration_ms=42,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )


def test_report_reader_aggregates_existing_records_and_isolates_workspace(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{(tmp_path / 'reports.db').as_posix()}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_workspace("workspace-1", tmp_path))
        session.add(_workspace("workspace-2", tmp_path))
        session.add(
            DocumentRecord(
                id="document-1",
                workspace_id="workspace-1",
                name="requirements.md",
                relative_path="requirements.md",
                path_key="requirements.md",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            DocumentVersionRecord(
                id="version-1",
                document_id="document-1",
                workspace_id="workspace-1",
                version_number=1,
                sha256="a" * 64,
                size_bytes=10,
                status="passed",
                created_at=NOW,
            )
        )
        session.add(
            AnalysisRunRecord(
                id="analysis-1",
                workspace_id="workspace-1",
                document_id="document-1",
                version_id="version-1",
                provider="ollama",
                model_name="qwen",
                base_url="http://127.0.0.1:11434",
                status="passed",
                progress=100,
                overall_score=86,
                created_at=NOW,
                finished_at=NOW,
            )
        )
        session.add(
            AnalysisIssueRecord(
                id="issue-1",
                run_id="analysis-1",
                ordinal=0,
                dimension="clarity",
                severity="medium",
                title="退款期限不清晰",
                description="缺少期限",
                impact="无法断言",
                suggestion="补充期限",
                question="期限是多少?",
            )
        )
        session.add(
            PointRecord(
                id="point-1",
                run_id="analysis-1",
                source_issue_id="issue-1",
                title="退款期限",
                objective="验证期限",
                test_type="boundary",
                priority="P1",
                status="confirmed",
                automation_candidate=True,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            CaseRecord(
                id="case-1",
                run_id="analysis-1",
                source_test_point_id="point-1",
                title="退款期限用例",
                preconditions_json="[]",
                priority="P1",
                tags_json="[]",
                automation_type="api",
                status="draft",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(_http_run("http-1", "workspace-1"))
        session.add(_http_run("http-2", "workspace-2"))
        session.add(
            HttpExecutionEventRecord(
                id="event-1",
                run_id="http-1",
                ordinal=0,
                level="info",
                code="HTTP_REQUEST_FINISHED",
                message="请求完成。",
                created_at=NOW,
            )
        )
        session.commit()

    report = SqlModelReportReader(engine).read("workspace-1")

    assert [item.id for item in report.executions] == ["http-1"]
    assert report.executions[0].response_summary == "HTTP 200 · 2 B · 断言 0/0"
    assert report.analysis_summary.total == 1
    assert report.analysis_summary.passed == 1
    assert report.analysis_summary.latest_overall_score == 86
    assert report.analysis_summary.issue_count == 1
    assert report.design_summary.test_point_confirmed == 1
    assert report.design_summary.test_case_total == 1
    exported_view = repr(report)
    assert "never-export-this-body" not in exported_view
    assert "never-export-this-response" not in exported_view
    assert "API_TOKEN" not in exported_view

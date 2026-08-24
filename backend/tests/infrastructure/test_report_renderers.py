import json
from datetime import UTC, datetime

import pytest

from backend.app.domain.reports import (
    ReportAnalysisSummary,
    ReportDesignSummary,
    ReportEvent,
    ReportExecution,
    ReportSnapshot,
    build_report_snapshot,
)
from backend.app.infrastructure.report_renderers import SafeReportRenderer

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def snapshot() -> ReportSnapshot:
    return build_report_snapshot(
        workspace_id="workspace-1",
        workspace_name="支付 <核心>|项目",
        generated_at=NOW,
        executions=(
            ReportExecution(
                "http",
                "run-1",
                "恶意 <script>alert(1)</script> | 标题",
                "error",
                123,
                "GET /pay Authorization: Bearer top-secret",
                "HTTP 500 · user@example.com · 13800138000",
                "HTTP_EXECUTION_ERROR",
                "token=abc123 password: letmein",
                NOW,
                NOW,
                (ReportEvent("error", "FAILED", "Cookie: session-value", NOW),),
            ),
        ),
        analysis_summary=ReportAnalysisSummary(1, 0, 1, None, 2),
        design_summary=ReportDesignSummary(2, 1, 1, 0),
    )


@pytest.mark.parametrize("format_name", ["json", "markdown", "html"])
def test_renderer_outputs_supported_formats_without_sensitive_values(format_name: str) -> None:
    artifact = SafeReportRenderer().render(snapshot(), format_name)  # type: ignore[arg-type]

    assert artifact.format == format_name
    assert artifact.file_name.endswith(
        {"json": ".json", "markdown": ".md", "html": ".html"}[format_name]
    )
    assert "top-secret" not in artifact.content
    assert "abc123" not in artifact.content
    assert "letmein" not in artifact.content
    assert "session-value" not in artifact.content
    assert "user@example.com" not in artifact.content
    assert "13800138000" not in artifact.content
    assert "***" in artifact.content

    if format_name == "json":
        payload = json.loads(artifact.content)
        assert payload["schema_version"] == 2
        assert payload["workspace_id"] == "workspace-1"
        assert len(payload["trend"]) == 14
        assert payload["failure_attribution_summary"]["total"] == 1
    elif format_name == "html":
        assert "<script>alert(1)</script>" not in artifact.content
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in artifact.content
        assert "最近 14 日趋势" in artifact.content
        assert "失败归因" in artifact.content
        assert "不调用模型" in artifact.content
    else:
        assert "\\|" in artifact.content
        assert "最近 14 日趋势" in artifact.content
        assert "失败归因" in artifact.content


def test_renderer_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="format"):
        SafeReportRenderer().render(snapshot(), "pdf")  # type: ignore[arg-type]

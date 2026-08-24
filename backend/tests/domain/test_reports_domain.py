from datetime import UTC, datetime, timedelta, timezone

from backend.app.domain.reports import (
    ReportAnalysisSummary,
    ReportDesignSummary,
    ReportEvent,
    ReportExecution,
    build_report_snapshot,
)

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def execution(
    identifier: str,
    status: str,
    *,
    duration_ms: int | None = None,
    request_summary: str = "GET /health",
    error_code: str | None = None,
    error_message: str | None = None,
    finished_at: datetime | None = NOW,
) -> ReportExecution:
    return ReportExecution(
        execution_type="http",
        id=identifier,
        name=f"HTTP {identifier}",
        status=status,  # type: ignore[arg-type]
        duration_ms=duration_ms,
        request_summary=request_summary,
        response_summary="HTTP 200 · 2 B",
        error_code=error_code,
        error_message=error_message,
        created_at=NOW - timedelta(minutes=1),
        finished_at=finished_at,
        events=(ReportEvent("info", "REQUEST_FINISHED", "请求完成。", NOW),),
    )


def test_report_snapshot_calculates_terminal_pass_rate_and_slowest_runs() -> None:
    snapshot = build_report_snapshot(
        workspace_id="workspace-1",
        workspace_name="支付项目",
        generated_at=NOW,
        executions=(
            execution("running", "running"),
            execution("passed", "passed", duration_ms=120),
            execution("failed", "failed", duration_ms=320),
            execution("error", "error", duration_ms=80),
            execution("cancelled", "cancelled"),
            execution("timeout", "timeout", duration_ms=500),
        ),
        analysis_summary=ReportAnalysisSummary(2, 1, 1, 88, 3),
        design_summary=ReportDesignSummary(4, 2, 3, 1),
    )

    assert snapshot.execution_summary.total == 6
    assert snapshot.execution_summary.passed == 1
    assert snapshot.execution_summary.failed == 1
    assert snapshot.execution_summary.error == 1
    assert snapshot.execution_summary.cancelled == 1
    assert snapshot.execution_summary.timeout == 1
    assert snapshot.execution_summary.active == 1
    assert snapshot.execution_summary.terminal == 5
    assert snapshot.execution_summary.evaluated == 4
    assert snapshot.execution_summary.pass_rate == 25.0
    assert snapshot.execution_summary.average_duration_ms == 255
    assert [item.id for item in snapshot.slow_executions] == [
        "timeout",
        "failed",
        "passed",
        "error",
    ]


def test_report_snapshot_builds_14_day_utc_trend_without_active_or_cancelled_denominator() -> None:
    local_time = datetime(2026, 8, 16, 0, 30, tzinfo=timezone(timedelta(hours=8)))
    snapshot = build_report_snapshot(
        workspace_id="workspace-1",
        workspace_name="支付项目",
        generated_at=NOW,
        executions=(
            execution("passed-today", "passed", duration_ms=120, finished_at=NOW),
            execution("failed-today", "failed", duration_ms=320, finished_at=NOW),
            execution("error-yesterday", "error", duration_ms=80, finished_at=local_time),
            execution("cancelled-yesterday", "cancelled", finished_at=local_time),
            execution("running", "running", finished_at=None),
            execution("missing-finish", "failed", finished_at=None),
        ),
        analysis_summary=ReportAnalysisSummary(0, 0, 0, None, 0),
        design_summary=ReportDesignSummary(0, 0, 0, 0),
    )

    assert len(snapshot.trend) == 14
    assert snapshot.trend[0].date.isoformat() == "2026-08-03"
    assert snapshot.trend[-1].date.isoformat() == "2026-08-16"
    yesterday = snapshot.trend[-2]
    assert (yesterday.error, yesterday.cancelled, yesterday.evaluated) == (1, 1, 1)
    assert yesterday.pass_rate == 0.0
    today = snapshot.trend[-1]
    assert (today.passed, today.failed, today.evaluated) == (1, 1, 2)
    assert today.pass_rate == 50.0
    assert today.average_duration_ms == 220


def test_report_snapshot_attributes_failures_by_stable_status_and_error_code() -> None:
    snapshot = build_report_snapshot(
        workspace_id="workspace-1",
        workspace_name="支付项目",
        generated_at=NOW,
        executions=(
            execution("product", "failed", error_code="HTTP_ASSERTION_FAILED"),
            execution("environment", "error", error_code="HTTP_TARGET_UNAVAILABLE"),
            execution("timeout", "timeout", error_code="HTTP_WORKER_ERROR"),
            execution("data", "failed", error_code="PROTO_DECODE_FAILED"),
            execution("script", "error", error_code="WEBSOCKET_TEMPLATE_INVALID"),
            execution("unknown", "error", error_code="HTTP_REQUEST_FAILED"),
            execution("cancelled", "cancelled", error_code="HTTP_TARGET_UNAVAILABLE"),
            execution("passed", "passed"),
        ),
        analysis_summary=ReportAnalysisSummary(0, 0, 0, None, 0),
        design_summary=ReportDesignSummary(0, 0, 0, 0),
    )

    assert snapshot.failure_attribution_summary.total == 6
    assert snapshot.failure_attribution_summary.product == 1
    assert snapshot.failure_attribution_summary.environment == 2
    assert snapshot.failure_attribution_summary.data == 1
    assert snapshot.failure_attribution_summary.script == 1
    assert snapshot.failure_attribution_summary.unknown == 1
    by_id = {item.execution_id: item for item in snapshot.failure_attributions}
    assert by_id["product"].rule_id == "ATTR_PRODUCT_ASSERTION"
    assert by_id["environment"].category == "environment"
    assert by_id["timeout"].rule_id == "ATTR_ENV_TIMEOUT"
    assert by_id["data"].category == "data"
    assert by_id["script"].category == "script"
    assert by_id["unknown"].rule_id == "ATTR_UNKNOWN"
    assert "cancelled" not in by_id


def test_report_snapshot_rejects_cross_workspace_unsafe_or_invalid_values() -> None:
    try:
        execution("bad", "passed", duration_ms=-1)
    except ValueError as exception:
        assert "duration" in str(exception)
    else:
        raise AssertionError("negative duration must be rejected")

    try:
        build_report_snapshot(
            workspace_id="workspace-1",
            workspace_name=" ",
            generated_at=NOW,
            executions=(),
            analysis_summary=ReportAnalysisSummary(0, 0, 0, None, 0),
            design_summary=ReportDesignSummary(0, 0, 0, 0),
        )
    except ValueError as exception:
        assert "workspace" in str(exception)
    else:
        raise AssertionError("invalid report must be rejected")

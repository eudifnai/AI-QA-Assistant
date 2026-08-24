# ruff: noqa: RUF001

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

ReportFormat = Literal["json", "markdown", "html"]
ExecutionType = Literal["http", "websocket", "protobuf"]
ExecutionStatus = Literal[
    "pending",
    "queued",
    "running",
    "passed",
    "failed",
    "error",
    "cancelled",
    "timeout",
]
EventLevel = Literal["info", "warning", "error"]
FailureCategory = Literal["product", "environment", "data", "script", "unknown"]

_EXECUTION_STATUSES = frozenset(
    {"pending", "queued", "running", "passed", "failed", "error", "cancelled", "timeout"}
)
_ACTIVE_STATUSES: frozenset[ExecutionStatus] = frozenset({"pending", "queued", "running"})
_TERMINAL_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {"passed", "failed", "error", "cancelled", "timeout"}
)
_EVALUATED_STATUSES: frozenset[ExecutionStatus] = frozenset(
    {"passed", "failed", "error", "timeout"}
)
_FAILURE_STATUSES: frozenset[ExecutionStatus] = frozenset({"failed", "error", "timeout"})


@dataclass(frozen=True, slots=True)
class ReportEvent:
    level: EventLevel
    code: str
    message: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.level not in {"info", "warning", "error"}:
            raise ValueError("invalid report event level")
        if not self.code.strip() or not self.message.strip():
            raise ValueError("report event code and message are required")


@dataclass(frozen=True, slots=True)
class ReportExecution:
    execution_type: ExecutionType
    id: str
    name: str
    status: ExecutionStatus
    duration_ms: int | None
    request_summary: str
    response_summary: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    events: tuple[ReportEvent, ...]

    def __post_init__(self) -> None:
        if self.execution_type not in {"http", "websocket", "protobuf"}:
            raise ValueError("invalid report execution type")
        if self.status not in _EXECUTION_STATUSES:
            raise ValueError("invalid report execution status")
        if not self.id.strip() or not self.name.strip() or not self.request_summary.strip():
            raise ValueError("report execution identity and request summary are required")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("report execution duration must be non-negative")


@dataclass(frozen=True, slots=True)
class ReportExecutionSummary:
    total: int
    passed: int
    failed: int
    error: int
    cancelled: int
    timeout: int
    active: int
    terminal: int
    evaluated: int
    pass_rate: float
    average_duration_ms: int | None


@dataclass(frozen=True, slots=True)
class ReportTrendPoint:
    date: date
    passed: int
    failed: int
    error: int
    cancelled: int
    timeout: int
    terminal: int
    evaluated: int
    pass_rate: float
    average_duration_ms: int | None


@dataclass(frozen=True, slots=True)
class FailureAttribution:
    execution_type: ExecutionType
    execution_id: str
    execution_name: str
    status: ExecutionStatus
    error_code: str | None
    category: FailureCategory
    rule_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class FailureAttributionSummary:
    total: int
    product: int
    environment: int
    data: int
    script: int
    unknown: int


@dataclass(frozen=True, slots=True)
class ReportAnalysisSummary:
    total: int
    passed: int
    failed_or_error: int
    latest_overall_score: int | None
    issue_count: int

    def __post_init__(self) -> None:
        values = (self.total, self.passed, self.failed_or_error, self.issue_count)
        if any(value < 0 for value in values):
            raise ValueError("report analysis counts must be non-negative")
        if self.latest_overall_score is not None and not 0 <= self.latest_overall_score <= 100:
            raise ValueError("report analysis score must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class ReportDesignSummary:
    test_point_total: int
    test_point_confirmed: int
    test_case_total: int
    test_case_confirmed: int

    def __post_init__(self) -> None:
        if any(
            value < 0
            for value in (
                self.test_point_total,
                self.test_point_confirmed,
                self.test_case_total,
                self.test_case_confirmed,
            )
        ):
            raise ValueError("report design counts must be non-negative")


@dataclass(frozen=True, slots=True)
class ReportData:
    executions: tuple[ReportExecution, ...]
    analysis_summary: ReportAnalysisSummary
    design_summary: ReportDesignSummary


@dataclass(frozen=True, slots=True)
class ReportSnapshot:
    schema_version: int
    workspace_id: str
    workspace_name: str
    generated_at: datetime
    execution_summary: ReportExecutionSummary
    analysis_summary: ReportAnalysisSummary
    design_summary: ReportDesignSummary
    trend: tuple[ReportTrendPoint, ...]
    failure_attribution_summary: FailureAttributionSummary
    failure_attributions: tuple[FailureAttribution, ...]
    slow_executions: tuple[ReportExecution, ...]
    executions: tuple[ReportExecution, ...]


@dataclass(frozen=True, slots=True)
class ReportArtifact:
    format: ReportFormat
    file_name: str
    media_type: str
    content: str
    generated_at: datetime


def _build_trend(
    executions: tuple[ReportExecution, ...], generated_at: datetime
) -> tuple[ReportTrendPoint, ...]:
    end_date = generated_at.astimezone(UTC).date()
    dates = tuple(end_date - timedelta(days=offset) for offset in reversed(range(14)))
    points: list[ReportTrendPoint] = []
    for trend_date in dates:
        items = tuple(
            item
            for item in executions
            if item.status in _TERMINAL_STATUSES
            and item.finished_at is not None
            and item.finished_at.astimezone(UTC).date() == trend_date
        )
        counts = Counter(item.status for item in items)
        evaluated = sum(counts[status] for status in _EVALUATED_STATUSES)
        durations = [
            item.duration_ms
            for item in items
            if item.status in _EVALUATED_STATUSES and item.duration_ms is not None
        ]
        points.append(
            ReportTrendPoint(
                date=trend_date,
                passed=counts["passed"],
                failed=counts["failed"],
                error=counts["error"],
                cancelled=counts["cancelled"],
                timeout=counts["timeout"],
                terminal=len(items),
                evaluated=evaluated,
                pass_rate=(0.0 if evaluated == 0 else round(counts["passed"] * 100 / evaluated, 2)),
                average_duration_ms=(
                    None if not durations else round(sum(durations) / len(durations))
                ),
            )
        )
    return tuple(points)


def _attribute_failure(item: ReportExecution) -> FailureAttribution:
    code = (item.error_code or "").upper()
    category: FailureCategory
    rule_id: str
    reason: str
    if item.status == "timeout" or "TIMEOUT" in code:
        category, rule_id = "environment", "ATTR_ENV_TIMEOUT"
        reason = "执行因目标等待或监督超时终止，建议先检查环境可用性与超时设置。"
    elif "ASSERT" in code:
        category, rule_id = "product", "ATTR_PRODUCT_ASSERTION"
        reason = "目标行为未满足已保存断言，建议核对产品行为与已确认预期。"
    elif any(
        marker in code
        for marker in (
            "UNAVAILABLE",
            "CONNECTION",
            "HANDSHAKE",
            "TLS",
            "DNS",
            "CREDENTIAL_STORE",
            "SECRET_MISSING",
            "WORKER",
            "INTERRUPTED",
            "CRASHED",
            "START_FAILED",
        )
    ):
        category, rule_id = "environment", "ATTR_ENV_RUNTIME"
        reason = "稳定错误码指向目标、凭据库或执行进程不可用，建议先检查运行环境。"
    elif any(
        marker in code
        for marker in (
            "DECODE",
            "ENCODE",
            "RESPONSE_TOO_LARGE",
            "MESSAGE_TOO_LARGE",
            "SCHEMA",
        )
    ):
        category, rule_id = "data", "ATTR_DATA_RESPONSE"
        reason = "稳定错误码指向响应大小、结构或编解码问题，建议核对接口数据与协议版本。"
    elif any(
        marker in code
        for marker in (
            "TEMPLATE",
            "VARIABLE",
            "INPUT_UNAVAILABLE",
            "REQUEST_INVALID",
            "METHOD_INVALID",
            "PATH_INVALID",
            "HEADERS_INVALID",
            "ASSET",
            "DESCRIPTOR",
        )
    ):
        category, rule_id = "script", "ATTR_SCRIPT_CONFIGURATION"
        reason = "稳定错误码指向模板、输入或执行配置，建议检查测试脚本与冻结配置。"
    elif code in {"HTTP_REQUEST_FAILED", "WEBSOCKET_REQUEST_FAILED", "PROTO_REQUEST_FAILED"}:
        category, rule_id = "unknown", "ATTR_UNKNOWN"
        reason = "现有稳定错误码不足以可靠区分原因，需要人工复核执行上下文。"
    elif item.status == "failed":
        category, rule_id = "product", "ATTR_PRODUCT_FAILED"
        reason = "执行已完成但验证未通过，暂归为产品行为偏差并建议人工复核。"
    else:
        category, rule_id = "unknown", "ATTR_UNKNOWN"
        reason = "现有稳定错误码不足以可靠区分原因，需要人工复核执行上下文。"
    return FailureAttribution(
        item.execution_type,
        item.id,
        item.name,
        item.status,
        item.error_code,
        category,
        rule_id,
        reason,
    )


def _build_failure_attributions(
    executions: tuple[ReportExecution, ...],
) -> tuple[FailureAttributionSummary, tuple[FailureAttribution, ...]]:
    attributions = tuple(
        _attribute_failure(item) for item in executions if item.status in _FAILURE_STATUSES
    )
    counts = Counter(item.category for item in attributions)
    return (
        FailureAttributionSummary(
            total=len(attributions),
            product=counts["product"],
            environment=counts["environment"],
            data=counts["data"],
            script=counts["script"],
            unknown=counts["unknown"],
        ),
        attributions,
    )


def build_report_snapshot(
    *,
    workspace_id: str,
    workspace_name: str,
    generated_at: datetime,
    executions: tuple[ReportExecution, ...],
    analysis_summary: ReportAnalysisSummary,
    design_summary: ReportDesignSummary,
) -> ReportSnapshot:
    if not workspace_id.strip() or not workspace_name.strip():
        raise ValueError("report workspace identity is required")
    if generated_at.utcoffset() is None:
        raise ValueError("report generation time must include a timezone")

    ordered = tuple(sorted(executions, key=lambda item: (item.created_at, item.id), reverse=True))
    counts = {
        status: sum(item.status == status for item in ordered) for status in _EXECUTION_STATUSES
    }
    terminal = sum(counts[status] for status in _TERMINAL_STATUSES)
    evaluated = sum(counts[status] for status in _EVALUATED_STATUSES)
    durations = [
        item.duration_ms
        for item in ordered
        if item.status in _EVALUATED_STATUSES and item.duration_ms is not None
    ]
    average_duration = None if not durations else round(sum(durations) / len(durations))
    slow = tuple(
        sorted(
            (item for item in ordered if item.duration_ms is not None),
            key=lambda item: (item.duration_ms or 0, item.created_at, item.id),
            reverse=True,
        )[:10]
    )
    summary = ReportExecutionSummary(
        total=len(ordered),
        passed=counts["passed"],
        failed=counts["failed"],
        error=counts["error"],
        cancelled=counts["cancelled"],
        timeout=counts["timeout"],
        active=sum(counts[status] for status in _ACTIVE_STATUSES),
        terminal=terminal,
        evaluated=evaluated,
        pass_rate=0.0 if evaluated == 0 else round(counts["passed"] * 100 / evaluated, 2),
        average_duration_ms=average_duration,
    )
    failure_summary, failure_attributions = _build_failure_attributions(ordered)
    return ReportSnapshot(
        schema_version=2,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        generated_at=generated_at,
        execution_summary=summary,
        analysis_summary=analysis_summary,
        design_summary=design_summary,
        trend=_build_trend(ordered, generated_at),
        failure_attribution_summary=failure_summary,
        failure_attributions=failure_attributions,
        slow_executions=slow,
        executions=ordered,
    )

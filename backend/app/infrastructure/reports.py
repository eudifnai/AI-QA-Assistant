from __future__ import annotations

from collections import Counter

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from backend.app.domain.http_execution import HttpExecution
from backend.app.domain.protobuf_execution import ProtoExecution
from backend.app.domain.reports import (
    ReportAnalysisSummary,
    ReportData,
    ReportDesignSummary,
    ReportEvent,
    ReportExecution,
)
from backend.app.domain.websocket_execution import WebSocketExecution
from backend.app.infrastructure.analysis import AnalysisIssueRecord, AnalysisRunRecord
from backend.app.infrastructure.http_execution import SqlModelHttpExecutionRepository
from backend.app.infrastructure.protobuf_execution import SqlModelProtoExecutionRepository
from backend.app.infrastructure.test_design import TestCaseRecord, TestPointRecord
from backend.app.infrastructure.websocket_execution import SqlModelWebSocketExecutionRepository


def _target(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


class SqlModelReportReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._http = SqlModelHttpExecutionRepository(engine)
        self._websocket = SqlModelWebSocketExecutionRepository(engine)
        self._protobuf = SqlModelProtoExecutionRepository(engine)

    def read(self, workspace_id: str) -> ReportData:
        executions = (
            *(self._http_execution(item) for item in self._http.list_runs(workspace_id)),
            *(self._websocket_execution(item) for item in self._websocket.list_runs(workspace_id)),
            *(self._protobuf_execution(item) for item in self._protobuf.list_runs(workspace_id)),
        )
        with Session(self._engine) as session:
            analysis_rows = session.exec(
                select(AnalysisRunRecord)
                .where(AnalysisRunRecord.workspace_id == workspace_id)
                .order_by(col(AnalysisRunRecord.created_at).desc())
            ).all()
            run_ids = [item.id for item in analysis_rows]
            issue_count = 0
            point_statuses: list[str] = []
            case_statuses: list[str] = []
            if run_ids:
                issue_count = len(
                    session.exec(
                        select(AnalysisIssueRecord.id).where(
                            col(AnalysisIssueRecord.run_id).in_(run_ids)
                        )
                    ).all()
                )
                point_statuses = list(
                    session.exec(
                        select(TestPointRecord.status).where(
                            col(TestPointRecord.run_id).in_(run_ids)
                        )
                    ).all()
                )
                case_statuses = list(
                    session.exec(
                        select(TestCaseRecord.status).where(col(TestCaseRecord.run_id).in_(run_ids))
                    ).all()
                )

        analysis_counts = Counter(item.status for item in analysis_rows)
        latest_score = next(
            (
                item.overall_score
                for item in analysis_rows
                if item.status == "passed" and item.overall_score is not None
            ),
            None,
        )
        return ReportData(
            executions=tuple(executions),
            analysis_summary=ReportAnalysisSummary(
                total=len(analysis_rows),
                passed=analysis_counts["passed"],
                failed_or_error=analysis_counts["failed"] + analysis_counts["error"],
                latest_overall_score=latest_score,
                issue_count=issue_count,
            ),
            design_summary=ReportDesignSummary(
                test_point_total=len(point_statuses),
                test_point_confirmed=sum(status == "confirmed" for status in point_statuses),
                test_case_total=len(case_statuses),
                test_case_confirmed=sum(status == "confirmed" for status in case_statuses),
            ),
        )

    @staticmethod
    def _http_execution(item: HttpExecution) -> ReportExecution:
        assertion_total = len(item.assertion_results)
        assertion_passed = sum(result.passed for result in item.assertion_results)
        response = None
        if item.response_status_code is not None:
            response = (
                f"HTTP {item.response_status_code} · {item.response_size_bytes or 0} B"
                f" · 断言 {assertion_passed}/{assertion_total}"
            )
        return ReportExecution(
            "http",
            item.id,
            f"{item.method} {item.path_template}",
            item.status,
            item.duration_ms,
            f"{item.environment_name} · {_target(item.base_url, item.path_template)}",
            response,
            item.error_code,
            item.error_message,
            item.created_at,
            item.finished_at,
            tuple(
                ReportEvent(event.level, event.code, event.message, event.created_at)
                for event in item.events
            ),
        )

    @staticmethod
    def _websocket_execution(item: WebSocketExecution) -> ReportExecution:
        assertion_total = len(item.assertion_results)
        assertion_passed = sum(result.passed for result in item.assertion_results)
        response = None
        if item.responses or item.response_message is not None:
            response = (
                f"接收 {len(item.responses) or 1} 条 · {item.response_size_bytes or 0} B"
                f" · 连接 {item.attempt_count} 次 · 断言 {assertion_passed}/{assertion_total}"
            )
        return ReportExecution(
            "websocket",
            item.id,
            f"WebSocket {item.path_template}",
            item.status,
            item.duration_ms,
            f"{item.environment_name} · {_target(item.base_url, item.path_template)}",
            response,
            item.error_code,
            item.error_message,
            item.created_at,
            item.finished_at,
            tuple(
                ReportEvent(event.level, event.code, event.message, event.created_at)
                for event in item.events
            ),
        )

    @staticmethod
    def _protobuf_execution(item: ProtoExecution) -> ReportExecution:
        assertion_total = len(item.assertion_results)
        assertion_passed = sum(result.passed for result in item.assertion_results)
        response = None
        if item.response_status_code is not None:
            response = (
                f"HTTP {item.response_status_code} · {item.response_size_bytes or 0} B"
                f" · 断言 {assertion_passed}/{assertion_total}"
            )
        return ReportExecution(
            "protobuf",
            item.id,
            f"{item.service_name}/{item.method_name}",
            item.status,
            item.duration_ms,
            f"{item.asset_name} · {_target(item.base_url, item.path_template)}",
            response,
            item.error_code,
            item.error_message,
            item.created_at,
            item.finished_at,
            tuple(
                ReportEvent(event.level, event.code, event.message, event.created_at)
                for event in item.events
            ),
        )

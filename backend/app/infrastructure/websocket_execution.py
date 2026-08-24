from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, col, select

from backend.app.domain.http_execution import HttpEnvironment
from backend.app.domain.websocket_execution import (
    TERMINAL_WEBSOCKET_EXECUTION_STATUSES,
    WebSocketEventLevel,
    WebSocketExecution,
    WebSocketExecutionEvent,
    WebSocketExecutionInput,
    WebSocketExecutionResult,
    WebSocketExecutionStartInput,
    WebSocketExecutionStatus,
    WebSocketMessage,
    WebSocketMessageAssertion,
    WebSocketMessageAssertionResult,
)
from backend.app.infrastructure.http_execution import HttpEnvironmentRecord  # noqa: F401
from backend.app.infrastructure.workspaces import WorkspaceRecord  # noqa: F401


class WebSocketExecutionRecord(SQLModel, table=True):
    __tablename__ = "websocket_executions"
    __table_args__ = (
        Index("ix_websocket_executions_workspace_created", "workspace_id", "created_at"),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    workspace_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        )
    )
    environment_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(36),
            ForeignKey("http_environments.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    environment_name: str = Field(sa_column=Column(String(120), nullable=False))
    base_url: str = Field(sa_column=Column(String(2048), nullable=False))
    path_template: str = Field(sa_column=Column(Text, nullable=False))
    headers_template_json: str = Field(sa_column=Column(Text, nullable=False))
    variables_json: str = Field(sa_column=Column(Text, nullable=False))
    secret_names_json: str = Field(sa_column=Column(Text, nullable=False))
    message_template: str = Field(sa_column=Column(Text, nullable=False))
    additional_messages_json: str = Field(
        default="[]", sa_column=Column(Text, nullable=False, server_default="[]")
    )
    receive_count: int = Field(
        default=1, sa_column=Column(Integer, nullable=False, server_default="1")
    )
    ping_interval_seconds: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )
    max_reconnect_attempts: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    responses_json: str = Field(
        default="[]", sa_column=Column(Text, nullable=False, server_default="[]")
    )
    assertions_json: str = Field(
        default="[]", sa_column=Column(Text, nullable=False, server_default="[]")
    )
    assertion_results_json: str = Field(
        default="[]", sa_column=Column(Text, nullable=False, server_default="[]")
    )
    attempt_count: int = Field(
        default=1, sa_column=Column(Integer, nullable=False, server_default="1")
    )
    timeout_seconds: int = Field(sa_column=Column(Integer, nullable=False))
    status: str = Field(sa_column=Column(String(16), nullable=False))
    progress: int = Field(sa_column=Column(Integer, nullable=False))
    pid: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    response_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    response_encoding: str | None = Field(default=None, sa_column=Column(String(16), nullable=True))
    response_size_bytes: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    duration_ms: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class WebSocketExecutionEventRecord(SQLModel, table=True):
    __tablename__ = "websocket_execution_events"
    __table_args__ = (
        Index("uq_websocket_execution_events_run_ordinal", "run_id", "ordinal", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    run_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("websocket_executions.id", ondelete="CASCADE"), nullable=False
        )
    )
    ordinal: int = Field(sa_column=Column(Integer, nullable=False))
    level: str = Field(sa_column=Column(String(16), nullable=False))
    code: str = Field(sa_column=Column(String(64), nullable=False))
    message: str = Field(sa_column=Column(String(500), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _mapping(value: str) -> dict[str, str]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in parsed.items()
    ):
        raise ValueError("invalid persisted WebSocket mapping")
    return parsed


def _names(value: str) -> tuple[str, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("invalid persisted WebSocket secret names")
    return tuple(parsed)


def _assertions(value: str) -> tuple[WebSocketMessageAssertion, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("invalid persisted WebSocket assertions")
    return tuple(
        WebSocketMessageAssertion(
            int(item["message_index"]),
            cast(Any, str(item["kind"])),
            None if item["path"] is None else str(item["path"]),
            str(item["expected"]),
        )
        for item in parsed
    )


def _responses(value: str) -> tuple[WebSocketMessage, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("invalid persisted WebSocket responses")
    return tuple(
        WebSocketMessage(
            int(item["ordinal"]),
            str(item["message"]),
            cast(Any, str(item["encoding"])),
            int(item["size_bytes"]),
        )
        for item in parsed
    )


def _assertion_results(value: str) -> tuple[WebSocketMessageAssertionResult, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("invalid persisted WebSocket assertion results")
    return tuple(
        WebSocketMessageAssertionResult(
            int(item["message_index"]),
            cast(Any, str(item["kind"])),
            None if item["path"] is None else str(item["path"]),
            str(item["expected"]),
            None if item["actual"] is None else str(item["actual"]),
            bool(item["passed"]),
            str(item["message"]),
        )
        for item in parsed
    )


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlModelWebSocketExecutionRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_run(
        self,
        *,
        run_id: str,
        workspace_id: str,
        environment: HttpEnvironment,
        input: WebSocketExecutionStartInput,
        created_at: datetime,
    ) -> WebSocketExecution:
        with Session(self._engine) as session:
            record = WebSocketExecutionRecord(
                id=run_id,
                workspace_id=workspace_id,
                environment_id=environment.id,
                environment_name=environment.name,
                base_url=environment.base_url,
                path_template=input.path,
                headers_template_json=_dump(input.headers),
                variables_json=_dump(environment.variables),
                secret_names_json=_dump(list(environment.secret_names)),
                message_template=input.message,
                additional_messages_json=_dump(list(input.additional_messages)),
                receive_count=input.receive_count,
                ping_interval_seconds=input.ping_interval_seconds,
                max_reconnect_attempts=input.max_reconnect_attempts,
                assertions_json=_dump(
                    [
                        {
                            "message_index": item.message_index,
                            "kind": item.kind,
                            "path": item.path,
                            "expected": item.expected,
                        }
                        for item in input.assertions
                    ]
                ),
                timeout_seconds=input.timeout_seconds,
                status="queued",
                progress=0,
                created_at=created_at,
            )
            session.add(record)
            self._add_event(
                session,
                run_id,
                "info",
                "WEBSOCKET_EXECUTION_QUEUED",
                "WebSocket 执行任务已进入队列。",
                created_at,
            )
            session.commit()
            session.refresh(record)
            return self._run(session, record)

    def list_runs(self, workspace_id: str) -> list[WebSocketExecution]:
        with Session(self._engine) as session:
            records = session.exec(
                select(WebSocketExecutionRecord)
                .where(WebSocketExecutionRecord.workspace_id == workspace_id)
                .order_by(col(WebSocketExecutionRecord.created_at).desc())
            ).all()
            return [self._run(session, record) for record in records]

    def get_run(self, workspace_id: str, run_id: str) -> WebSocketExecution | None:
        with Session(self._engine) as session:
            record = session.get(WebSocketExecutionRecord, run_id)
            if record is None or record.workspace_id != workspace_id:
                return None
            return self._run(session, record)

    def get_any(self, run_id: str) -> WebSocketExecution | None:
        with Session(self._engine) as session:
            record = session.get(WebSocketExecutionRecord, run_id)
            return None if record is None else self._run(session, record)

    def load_execution_input(self, run_id: str) -> WebSocketExecutionInput | None:
        with Session(self._engine) as session:
            record = session.get(WebSocketExecutionRecord, run_id)
            if record is None:
                return None
            return WebSocketExecutionInput(
                base_url=record.base_url,
                path_template=record.path_template,
                headers_template=_mapping(record.headers_template_json),
                variables=_mapping(record.variables_json),
                secret_names=_names(record.secret_names_json),
                message_template=record.message_template,
                timeout_seconds=record.timeout_seconds,
                additional_message_templates=_names(record.additional_messages_json),
                receive_count=record.receive_count,
                ping_interval_seconds=record.ping_interval_seconds,
                max_reconnect_attempts=record.max_reconnect_attempts,
                assertions=_assertions(record.assertions_json),
            )

    def mark_running(self, run_id: str, *, pid: int, now: datetime) -> None:
        self._transition(
            run_id,
            "running",
            35,
            now=now,
            pid=pid,
            event=("info", "WEBSOCKET_WORKER_STARTED", "WebSocket Worker 已启动并开始连接。"),
        )

    def mark_passed(self, run_id: str, *, result: WebSocketExecutionResult, now: datetime) -> None:
        assertions_passed = all(item.passed for item in result.assertion_results)
        status: WebSocketExecutionStatus = "passed" if assertions_passed else "failed"
        code = None if assertions_passed else "WEBSOCKET_ASSERTION_FAILED"
        message = None if assertions_passed else "一个或多个 WebSocket 消息序列断言未通过。"
        self._transition(
            run_id,
            status,
            100,
            now=now,
            result=result,
            code=code,
            message=message,
            event=(
                "info" if assertions_passed else "error",
                code or "WEBSOCKET_SEQUENCE_RECEIVED",
                message or f"已按顺序接收 {len(result.responses) or 1} 条 WebSocket 消息。",
            ),
        )

    def mark_failed(self, run_id: str, *, code: str, message: str, now: datetime) -> None:
        self._transition(
            run_id,
            "failed",
            100,
            now=now,
            code=code,
            message=message,
            event=("error", code, message),
        )

    def mark_error(self, run_id: str, *, code: str, message: str, now: datetime) -> None:
        self._transition(
            run_id,
            "error",
            100,
            now=now,
            code=code,
            message=message,
            event=("error", code, message),
        )

    def mark_cancelled(self, run_id: str, *, now: datetime) -> None:
        self._transition(
            run_id,
            "cancelled",
            100,
            now=now,
            code="WEBSOCKET_EXECUTION_CANCELLED",
            message="WebSocket 执行任务已取消。",
            event=("warning", "WEBSOCKET_EXECUTION_CANCELLED", "WebSocket 执行任务已取消。"),
        )

    def mark_timeout(self, run_id: str, *, now: datetime) -> None:
        self._transition(
            run_id,
            "timeout",
            100,
            now=now,
            code="WEBSOCKET_EXECUTION_TIMEOUT",
            message="WebSocket 执行任务超过总时限。",
            event=("error", "WEBSOCKET_EXECUTION_TIMEOUT", "WebSocket 执行任务超过总时限。"),
        )

    def recover_interrupted(self, *, now: datetime) -> None:
        with Session(self._engine) as session:
            records = session.exec(
                select(WebSocketExecutionRecord).where(
                    col(WebSocketExecutionRecord.status).in_(["queued", "running"])
                )
            ).all()
            for record in records:
                self._transition_record(
                    record,
                    "error",
                    100,
                    now=now,
                    code="WEBSOCKET_EXECUTION_INTERRUPTED",
                    message="应用重启时 WebSocket 任务仍未结束。",
                )
                self._add_event(
                    session,
                    record.id,
                    "error",
                    "WEBSOCKET_EXECUTION_INTERRUPTED",
                    "应用重启时 WebSocket 任务仍未结束。",
                    now,
                )
                session.add(record)
            session.commit()

    def _transition(
        self,
        run_id: str,
        status: WebSocketExecutionStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        code: str | None = None,
        message: str | None = None,
        result: WebSocketExecutionResult | None = None,
        event: tuple[WebSocketEventLevel, str, str] | None = None,
    ) -> None:
        with Session(self._engine) as session:
            record = session.get(WebSocketExecutionRecord, run_id)
            if record is None or record.status in TERMINAL_WEBSOCKET_EXECUTION_STATUSES:
                return
            self._transition_record(
                record,
                status,
                progress,
                now=now,
                pid=pid,
                code=code,
                message=message,
                result=result,
            )
            if event is not None:
                self._add_event(session, run_id, *event, now)
            session.add(record)
            session.commit()

    @staticmethod
    def _transition_record(
        record: WebSocketExecutionRecord,
        status: WebSocketExecutionStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        code: str | None = None,
        message: str | None = None,
        result: WebSocketExecutionResult | None = None,
    ) -> None:
        record.status = status
        record.progress = progress
        if pid is not None:
            record.pid = pid
        if status == "running" and record.started_at is None:
            record.started_at = now
        if status in TERMINAL_WEBSOCKET_EXECUTION_STATUSES:
            record.finished_at = now
        record.error_code = code
        record.error_message = message
        if result is not None:
            record.response_message = result.message
            record.response_encoding = result.encoding
            record.response_size_bytes = result.size_bytes
            record.duration_ms = result.duration_ms
            record.responses_json = _dump(
                [
                    {
                        "ordinal": item.ordinal,
                        "message": item.message,
                        "encoding": item.encoding,
                        "size_bytes": item.size_bytes,
                    }
                    for item in result.responses
                ]
            )
            record.assertion_results_json = _dump(
                [
                    {
                        "message_index": item.message_index,
                        "kind": item.kind,
                        "path": item.path,
                        "expected": item.expected,
                        "actual": item.actual,
                        "passed": item.passed,
                        "message": item.message,
                    }
                    for item in result.assertion_results
                ]
            )
            record.attempt_count = result.attempt_count

    @staticmethod
    def _add_event(
        session: Session,
        run_id: str,
        level: WebSocketEventLevel,
        code: str,
        message: str,
        now: datetime,
    ) -> None:
        latest = session.exec(
            select(WebSocketExecutionEventRecord)
            .where(WebSocketExecutionEventRecord.run_id == run_id)
            .order_by(col(WebSocketExecutionEventRecord.ordinal).desc())
        ).first()
        session.add(
            WebSocketExecutionEventRecord(
                id=str(uuid4()),
                run_id=run_id,
                ordinal=1 if latest is None else latest.ordinal + 1,
                level=level,
                code=code,
                message=message,
                created_at=now,
            )
        )

    @staticmethod
    def _run(session: Session, record: WebSocketExecutionRecord) -> WebSocketExecution:
        events = session.exec(
            select(WebSocketExecutionEventRecord)
            .where(WebSocketExecutionEventRecord.run_id == record.id)
            .order_by(col(WebSocketExecutionEventRecord.ordinal))
        ).all()
        raw_response_encoding = record.response_encoding
        if raw_response_encoding not in {None, "text", "base64"}:
            raise ValueError("invalid persisted WebSocket response encoding")
        response_encoding = cast(Literal["text", "base64"] | None, raw_response_encoding)
        responses = _responses(record.responses_json)
        if (
            not responses
            and record.response_message is not None
            and response_encoding is not None
            and record.response_size_bytes is not None
        ):
            responses = (
                WebSocketMessage(
                    0,
                    record.response_message,
                    response_encoding,
                    record.response_size_bytes,
                ),
            )
        status = cast(WebSocketExecutionStatus, record.status)
        return WebSocketExecution(
            id=record.id,
            workspace_id=record.workspace_id,
            environment_id=record.environment_id,
            environment_name=record.environment_name,
            base_url=record.base_url,
            path_template=record.path_template,
            headers_template=_mapping(record.headers_template_json),
            variables=_mapping(record.variables_json),
            secret_names=_names(record.secret_names_json),
            message_template=record.message_template,
            timeout_seconds=record.timeout_seconds,
            status=status,
            progress=record.progress,
            pid=record.pid,
            response_message=record.response_message,
            response_encoding=response_encoding,
            response_size_bytes=record.response_size_bytes,
            duration_ms=record.duration_ms,
            error_code=record.error_code,
            error_message=record.error_message,
            created_at=_utc(record.created_at) or record.created_at,
            started_at=_utc(record.started_at),
            finished_at=_utc(record.finished_at),
            events=tuple(
                WebSocketExecutionEvent(
                    id=item.id,
                    ordinal=item.ordinal,
                    level=cast(WebSocketEventLevel, item.level),
                    code=item.code,
                    message=item.message,
                    created_at=_utc(item.created_at) or item.created_at,
                )
                for item in events
            ),
            additional_message_templates=_names(record.additional_messages_json),
            receive_count=record.receive_count,
            ping_interval_seconds=record.ping_interval_seconds,
            max_reconnect_attempts=record.max_reconnect_attempts,
            responses=responses,
            assertions=_assertions(record.assertions_json),
            assertion_results=_assertion_results(record.assertion_results_json),
            attempt_count=record.attempt_count,
        )

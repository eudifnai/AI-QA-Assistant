from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, col, select

from backend.app.domain.http_execution import HttpEnvironment
from backend.app.domain.proto_asset import ProtoAsset
from backend.app.domain.protobuf_execution import (
    TERMINAL_PROTO_EXECUTION_STATUSES,
    ProtoEventLevel,
    ProtoExecution,
    ProtoExecutionEvent,
    ProtoExecutionInput,
    ProtoExecutionResult,
    ProtoExecutionStartInput,
    ProtoExecutionStatus,
    ProtoFieldAssertion,
    ProtoFieldAssertionResult,
)
from backend.app.infrastructure.http_execution import HttpEnvironmentRecord  # noqa: F401
from backend.app.infrastructure.proto_assets import ProtoAssetRecord  # noqa: F401
from backend.app.infrastructure.workspaces import WorkspaceRecord  # noqa: F401


class ProtoExecutionRecord(SQLModel, table=True):
    __tablename__ = "protobuf_executions"
    __table_args__ = (
        Index("ix_protobuf_executions_workspace_created", "workspace_id", "created_at"),
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
            String(36), ForeignKey("http_environments.id", ondelete="SET NULL"), nullable=True
        ),
    )
    environment_name: str = Field(sa_column=Column(String(120), nullable=False))
    asset_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(36), ForeignKey("proto_assets.id", ondelete="SET NULL"), nullable=True
        ),
    )
    asset_name: str = Field(sa_column=Column(String(255), nullable=False))
    asset_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    descriptor_set: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    service_name: str = Field(sa_column=Column(String(255), nullable=False))
    method_name: str = Field(sa_column=Column(String(255), nullable=False))
    request_message_type: str = Field(sa_column=Column(String(255), nullable=False))
    response_message_type: str = Field(sa_column=Column(String(255), nullable=False))
    base_url: str = Field(sa_column=Column(String(2048), nullable=False))
    path_template: str = Field(sa_column=Column(Text, nullable=False))
    headers_template_json: str = Field(sa_column=Column(Text, nullable=False))
    variables_json: str = Field(sa_column=Column(Text, nullable=False))
    secret_names_json: str = Field(sa_column=Column(Text, nullable=False))
    request_payload_json: str = Field(sa_column=Column(Text, nullable=False))
    timeout_seconds: int = Field(sa_column=Column(Integer, nullable=False))
    assertions_json: str = Field(sa_column=Column(Text, nullable=False))
    assertion_results_json: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(sa_column=Column(String(16), nullable=False))
    progress: int = Field(sa_column=Column(Integer, nullable=False))
    pid: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    response_status_code: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    response_headers_json: str = Field(sa_column=Column(Text, nullable=False))
    response_payload_json: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    response_size_bytes: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    duration_ms: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class ProtoExecutionEventRecord(SQLModel, table=True):
    __tablename__ = "protobuf_execution_events"
    __table_args__ = (
        Index("uq_protobuf_execution_events_run_ordinal", "run_id", "ordinal", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    run_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("protobuf_executions.id", ondelete="CASCADE"), nullable=False
        )
    )
    ordinal: int = Field(sa_column=Column(Integer, nullable=False))
    level: str = Field(sa_column=Column(String(16), nullable=False))
    code: str = Field(sa_column=Column(String(64), nullable=False))
    message: str = Field(sa_column=Column(String(500), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


def _dump(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def _object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("invalid persisted Protobuf object")
    return parsed


def _mapping(value: str) -> dict[str, str]:
    parsed = _object(value)
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in parsed.items()):
        raise ValueError("invalid persisted Protobuf mapping")
    return cast(dict[str, str], parsed)


def _names(value: str) -> tuple[str, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("invalid persisted Protobuf secret names")
    return tuple(parsed)


def _assertions(value: str) -> tuple[ProtoFieldAssertion, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("invalid persisted Protobuf assertions")
    return tuple(
        ProtoFieldAssertion(str(item["path"]), str(item["expected_json"])) for item in parsed
    )


def _results(value: str) -> tuple[ProtoFieldAssertionResult, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("invalid persisted Protobuf assertion results")
    return tuple(
        ProtoFieldAssertionResult(
            str(item["path"]),
            str(item["expected_json"]),
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


class SqlModelProtoExecutionRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_run(
        self,
        *,
        run_id: str,
        workspace_id: str,
        environment: HttpEnvironment,
        asset: ProtoAsset,
        input: ProtoExecutionStartInput,
        request_message_type: str,
        response_message_type: str,
        created_at: datetime,
    ) -> ProtoExecution:
        with Session(self._engine) as session:
            record = ProtoExecutionRecord(
                id=run_id,
                workspace_id=workspace_id,
                environment_id=environment.id,
                environment_name=environment.name,
                asset_id=asset.id,
                asset_name=asset.name,
                asset_sha256=asset.sha256,
                descriptor_set=asset.descriptor_set,
                service_name=input.service_name,
                method_name=input.method_name,
                request_message_type=request_message_type,
                response_message_type=response_message_type,
                base_url=environment.base_url,
                path_template=input.path,
                headers_template_json=_dump(input.headers),
                variables_json=_dump(environment.variables),
                secret_names_json=_dump(list(environment.secret_names)),
                request_payload_json=_dump(input.request_payload),
                timeout_seconds=input.timeout_seconds,
                assertions_json=_dump(
                    [
                        {"path": item.path, "expected_json": item.expected_json}
                        for item in input.assertions
                    ]
                ),
                assertion_results_json="[]",
                status="queued",
                progress=0,
                response_headers_json="{}",
                created_at=created_at,
            )
            session.add(record)
            self._add_event(
                session,
                run_id,
                "info",
                "PROTO_EXECUTION_QUEUED",
                "Protobuf 执行任务已进入队列。",
                created_at,
            )
            session.commit()
            session.refresh(record)
            return self._run(session, record)

    def list_runs(self, workspace_id: str) -> list[ProtoExecution]:
        with Session(self._engine) as session:
            records = session.exec(
                select(ProtoExecutionRecord)
                .where(ProtoExecutionRecord.workspace_id == workspace_id)
                .order_by(col(ProtoExecutionRecord.created_at).desc())
            ).all()
            return [self._run(session, item) for item in records]

    def get_run(self, workspace_id: str, run_id: str) -> ProtoExecution | None:
        with Session(self._engine) as session:
            record = session.get(ProtoExecutionRecord, run_id)
            return (
                None
                if record is None or record.workspace_id != workspace_id
                else self._run(session, record)
            )

    def get_any(self, run_id: str) -> ProtoExecution | None:
        with Session(self._engine) as session:
            record = session.get(ProtoExecutionRecord, run_id)
            return None if record is None else self._run(session, record)

    def load_execution_input(self, run_id: str) -> ProtoExecutionInput | None:
        with Session(self._engine) as session:
            record = session.get(ProtoExecutionRecord, run_id)
            if record is None or record.environment_id is None:
                return None
            return ProtoExecutionInput(
                run_id,
                record.environment_id,
                record.base_url,
                _mapping(record.variables_json),
                _names(record.secret_names_json),
                record.descriptor_set,
                record.path_template,
                _mapping(record.headers_template_json),
                record.request_message_type,
                record.response_message_type,
                _object(record.request_payload_json),
                record.timeout_seconds,
                _assertions(record.assertions_json),
            )

    def mark_running(self, run_id: str, *, pid: int, now: datetime) -> None:
        self._transition(
            run_id,
            "running",
            35,
            now=now,
            pid=pid,
            event=("info", "PROTO_WORKER_STARTED", "Protobuf Worker 已启动并开始发送。"),
        )

    def mark_completed(self, run_id: str, *, result: ProtoExecutionResult, now: datetime) -> None:
        status: ProtoExecutionStatus = (
            "passed"
            if 200 <= result.status_code < 300
            and all(item.passed for item in result.assertion_results)
            else "failed"
        )
        code = None
        message = None
        if not 200 <= result.status_code < 300:
            code, message = "PROTO_HTTP_STATUS_FAILED", "Protobuf 接口返回了非成功 HTTP 状态码。"
        elif not all(item.passed for item in result.assertion_results):
            code, message = "PROTO_ASSERTION_FAILED", "一个或多个 Protobuf 字段断言未通过。"
        self._transition(
            run_id,
            status,
            100,
            now=now,
            result=result,
            code=code,
            message=message,
            event=(
                ("info" if status == "passed" else "error"),
                code or "PROTO_EXECUTION_PASSED",
                message or "Protobuf 接口执行通过。",
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
            code="PROTO_EXECUTION_CANCELLED",
            message="Protobuf 执行任务已取消。",
            event=("warning", "PROTO_EXECUTION_CANCELLED", "Protobuf 执行任务已取消。"),
        )

    def mark_timeout(self, run_id: str, *, now: datetime) -> None:
        self._transition(
            run_id,
            "timeout",
            100,
            now=now,
            code="PROTO_EXECUTION_TIMEOUT",
            message="Protobuf 执行任务超过总时限。",
            event=("error", "PROTO_EXECUTION_TIMEOUT", "Protobuf 执行任务超过总时限。"),
        )

    def recover_interrupted(self, *, now: datetime) -> None:
        with Session(self._engine) as session:
            records = session.exec(
                select(ProtoExecutionRecord).where(
                    col(ProtoExecutionRecord.status).in_(["queued", "running"])
                )
            ).all()
            for record in records:
                self._transition_record(
                    record,
                    "error",
                    100,
                    now=now,
                    code="PROTO_EXECUTION_INTERRUPTED",
                    message="应用重启时 Protobuf 任务仍未结束。",
                )
                self._add_event(
                    session,
                    record.id,
                    "error",
                    "PROTO_EXECUTION_INTERRUPTED",
                    "应用重启时 Protobuf 任务仍未结束。",
                    now,
                )
                session.add(record)
            session.commit()

    def _transition(
        self,
        run_id: str,
        status: ProtoExecutionStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        code: str | None = None,
        message: str | None = None,
        result: ProtoExecutionResult | None = None,
        event: tuple[ProtoEventLevel, str, str] | None = None,
    ) -> None:
        with Session(self._engine) as session:
            record = session.get(ProtoExecutionRecord, run_id)
            if record is None or record.status in TERMINAL_PROTO_EXECUTION_STATUSES:
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
        record: ProtoExecutionRecord,
        status: ProtoExecutionStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        code: str | None = None,
        message: str | None = None,
        result: ProtoExecutionResult | None = None,
    ) -> None:
        record.status = status
        record.progress = progress
        if pid is not None:
            record.pid = pid
            record.started_at = now
        if result is not None:
            record.response_status_code = result.status_code
            record.response_headers_json = _dump(result.headers)
            record.response_payload_json = _dump(result.payload)
            record.response_size_bytes = result.size_bytes
            record.duration_ms = result.duration_ms
            record.assertion_results_json = _dump(
                [
                    {
                        "path": item.path,
                        "expected_json": item.expected_json,
                        "actual": item.actual,
                        "passed": item.passed,
                        "message": item.message,
                    }
                    for item in result.assertion_results
                ]
            )
        record.error_code = code
        record.error_message = message
        if status in TERMINAL_PROTO_EXECUTION_STATUSES:
            record.finished_at = now

    @staticmethod
    def _add_event(
        session: Session,
        run_id: str,
        level: ProtoEventLevel,
        code: str,
        message: str,
        now: datetime,
    ) -> None:
        latest = session.exec(
            select(ProtoExecutionEventRecord)
            .where(ProtoExecutionEventRecord.run_id == run_id)
            .order_by(col(ProtoExecutionEventRecord.ordinal).desc())
        ).first()
        session.add(
            ProtoExecutionEventRecord(
                id=str(uuid4()),
                run_id=run_id,
                ordinal=1 if latest is None else latest.ordinal + 1,
                level=level,
                code=code,
                message=message,
                created_at=now,
            )
        )

    def _run(self, session: Session, record: ProtoExecutionRecord) -> ProtoExecution:
        events = session.exec(
            select(ProtoExecutionEventRecord)
            .where(ProtoExecutionEventRecord.run_id == record.id)
            .order_by(col(ProtoExecutionEventRecord.ordinal))
        ).all()
        return ProtoExecution(
            record.id,
            record.workspace_id,
            record.environment_id,
            record.environment_name,
            record.asset_id,
            record.asset_name,
            record.asset_sha256,
            record.service_name,
            record.method_name,
            record.base_url,
            record.path_template,
            _mapping(record.headers_template_json),
            record.request_message_type,
            record.response_message_type,
            _object(record.request_payload_json),
            record.timeout_seconds,
            _assertions(record.assertions_json),
            _results(record.assertion_results_json),
            cast(ProtoExecutionStatus, record.status),
            record.progress,
            record.pid,
            record.response_status_code,
            _mapping(record.response_headers_json),
            None if record.response_payload_json is None else _object(record.response_payload_json),
            record.response_size_bytes,
            record.duration_ms,
            record.error_code,
            record.error_message,
            _utc(record.created_at) or record.created_at,
            _utc(record.started_at),
            _utc(record.finished_at),
            tuple(
                ProtoExecutionEvent(
                    item.id,
                    item.ordinal,
                    cast(ProtoEventLevel, item.level),
                    item.code,
                    item.message,
                    _utc(item.created_at) or item.created_at,
                )
                for item in events
            ),
        )

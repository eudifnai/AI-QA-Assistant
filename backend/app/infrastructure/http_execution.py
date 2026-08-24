from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, col, select

from backend.app.domain.http_execution import (
    TERMINAL_HTTP_EXECUTION_STATUSES,
    HttpAssertion,
    HttpAssertionResult,
    HttpEnvironment,
    HttpEnvironmentInput,
    HttpExecution,
    HttpExecutionEvent,
    HttpExecutionInput,
    HttpExecutionResult,
    HttpExecutionStartInput,
    HttpExecutionStatus,
)
from backend.app.infrastructure.workspaces import WorkspaceRecord  # noqa: F401


class HttpEnvironmentRecord(SQLModel, table=True):
    __tablename__ = "http_environments"
    __table_args__ = (
        Index("uq_http_environments_workspace_name", "workspace_id", "name_key", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    workspace_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        )
    )
    name: str = Field(sa_column=Column(String(120), nullable=False))
    name_key: str = Field(sa_column=Column(String(120), nullable=False))
    base_url: str = Field(sa_column=Column(String(2048), nullable=False))
    variables_json: str = Field(sa_column=Column(Text, nullable=False))
    secret_names_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class HttpExecutionRecord(SQLModel, table=True):
    __tablename__ = "http_executions"
    __table_args__ = (Index("ix_http_executions_workspace_created", "workspace_id", "created_at"),)

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
    variables_json: str = Field(sa_column=Column(Text, nullable=False))
    secret_names_json: str = Field(sa_column=Column(Text, nullable=False))
    method: str = Field(sa_column=Column(String(8), nullable=False))
    path_template: str = Field(sa_column=Column(String(4096), nullable=False))
    headers_template_json: str = Field(sa_column=Column(Text, nullable=False))
    body_template: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    timeout_seconds: int = Field(sa_column=Column(Integer, nullable=False))
    max_attempts: int = Field(sa_column=Column(Integer, nullable=False, server_default="1"))
    assertions_json: str = Field(sa_column=Column(Text, nullable=False, server_default="[]"))
    assertion_results_json: str = Field(sa_column=Column(Text, nullable=False, server_default="[]"))
    status: str = Field(sa_column=Column(String(16), nullable=False))
    progress: int = Field(sa_column=Column(Integer, nullable=False))
    pid: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    response_status_code: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    response_headers_json: str = Field(sa_column=Column(Text, nullable=False))
    response_body: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    response_body_encoding: str | None = Field(
        default=None, sa_column=Column(String(8), nullable=True)
    )
    response_size_bytes: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    duration_ms: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    error_code: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    error_message: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class HttpExecutionEventRecord(SQLModel, table=True):
    __tablename__ = "http_execution_events"
    __table_args__ = (
        Index("uq_http_execution_events_run_ordinal", "run_id", "ordinal", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    run_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("http_executions.id", ondelete="CASCADE"), nullable=False
        )
    )
    ordinal: int = Field(sa_column=Column(Integer, nullable=False))
    level: str = Field(sa_column=Column(String(16), nullable=False))
    code: str = Field(sa_column=Column(String(64), nullable=False))
    message: str = Field(sa_column=Column(String(500), nullable=False))
    attempt: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dict(value: str) -> dict[str, str]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in parsed.items()
    ):
        raise ValueError("invalid persisted mapping")
    return parsed


def _names(value: str) -> tuple[str, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("invalid persisted names")
    return tuple(parsed)


def _assertions(value: str) -> tuple[HttpAssertion, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("invalid persisted assertions")
    return tuple(
        HttpAssertion(str(item["kind"]), item.get("target"), str(item["expected"]))  # type: ignore[arg-type]
        for item in parsed
        if isinstance(item, dict)
    )


def _assertion_results(value: str) -> tuple[HttpAssertionResult, ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("invalid persisted assertion results")
    return tuple(
        HttpAssertionResult(
            str(item["kind"]),  # type: ignore[arg-type]
            item.get("target"),
            str(item["expected"]),
            item.get("actual"),
            bool(item["passed"]),
            str(item["message"]),
        )
        for item in parsed
        if isinstance(item, dict)
    )


def _dump_assertions(assertions: tuple[HttpAssertion, ...]) -> str:
    return _dump(
        [
            {"kind": item.kind, "target": item.target, "expected": item.expected}
            for item in assertions
        ]
    )


def _dump_assertion_results(results: tuple[HttpAssertionResult, ...]) -> str:
    return _dump(
        [
            {
                "kind": item.kind,
                "target": item.target,
                "expected": item.expected,
                "actual": item.actual,
                "passed": item.passed,
                "message": item.message,
            }
            for item in results
        ]
    )


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlModelHttpExecutionRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_environments(self, workspace_id: str) -> list[HttpEnvironment]:
        with Session(self._engine) as session:
            records = session.exec(
                select(HttpEnvironmentRecord)
                .where(HttpEnvironmentRecord.workspace_id == workspace_id)
                .order_by(col(HttpEnvironmentRecord.name_key))
            ).all()
            return [self._environment(record) for record in records]

    def get_environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment | None:
        with Session(self._engine) as session:
            record = session.get(HttpEnvironmentRecord, environment_id)
            if record is None or record.workspace_id != workspace_id:
                return None
            return self._environment(record)

    def find_environment_by_name(self, workspace_id: str, name_key: str) -> HttpEnvironment | None:
        with Session(self._engine) as session:
            record = session.exec(
                select(HttpEnvironmentRecord).where(
                    HttpEnvironmentRecord.workspace_id == workspace_id,
                    HttpEnvironmentRecord.name_key == name_key,
                )
            ).first()
            return None if record is None else self._environment(record)

    def create_environment(
        self,
        environment_id: str,
        workspace_id: str,
        input: HttpEnvironmentInput,
        *,
        now: datetime,
    ) -> HttpEnvironment:
        with Session(self._engine) as session:
            session.add(
                HttpEnvironmentRecord(
                    id=environment_id,
                    workspace_id=workspace_id,
                    name=input.name,
                    name_key=input.name.casefold(),
                    base_url=input.base_url,
                    variables_json=_dump(input.variables),
                    secret_names_json="[]",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        result = self.get_environment(workspace_id, environment_id)
        if result is None:
            raise RuntimeError("HTTP environment was not persisted")
        return result

    def update_environment(
        self,
        environment_id: str,
        input: HttpEnvironmentInput,
        *,
        now: datetime,
    ) -> HttpEnvironment:
        with Session(self._engine) as session:
            record = session.get(HttpEnvironmentRecord, environment_id)
            if record is None:
                raise LookupError(environment_id)
            workspace_id = record.workspace_id
            record.name = input.name
            record.name_key = input.name.casefold()
            record.base_url = input.base_url
            record.variables_json = _dump(input.variables)
            record.updated_at = now
            session.add(record)
            session.commit()
        result = self.get_environment(workspace_id, environment_id)
        if result is None:
            raise RuntimeError("HTTP environment was not updated")
        return result

    def delete_environment(self, environment_id: str) -> None:
        with Session(self._engine) as session:
            record = session.get(HttpEnvironmentRecord, environment_id)
            if record is None:
                raise LookupError(environment_id)
            session.delete(record)
            session.commit()

    def add_secret_name(self, environment_id: str, name: str, *, now: datetime) -> HttpEnvironment:
        return self._change_secret_name(environment_id, name, add=True, now=now)

    def remove_secret_name(
        self, environment_id: str, name: str, *, now: datetime
    ) -> HttpEnvironment:
        return self._change_secret_name(environment_id, name, add=False, now=now)

    def _change_secret_name(
        self, environment_id: str, name: str, *, add: bool, now: datetime
    ) -> HttpEnvironment:
        with Session(self._engine) as session:
            record = session.get(HttpEnvironmentRecord, environment_id)
            if record is None:
                raise LookupError(environment_id)
            workspace_id = record.workspace_id
            names = set(_names(record.secret_names_json))
            if add:
                names.add(name)
            else:
                names.discard(name)
            record.secret_names_json = _dump(sorted(names))
            record.updated_at = now
            session.add(record)
            session.commit()
        result = self.get_environment(workspace_id, environment_id)
        if result is None:
            raise RuntimeError("HTTP environment secret metadata was not persisted")
        return result

    def create_run(
        self,
        *,
        run_id: str,
        workspace_id: str,
        environment: HttpEnvironment,
        input: HttpExecutionStartInput,
        created_at: datetime,
    ) -> HttpExecution:
        with Session(self._engine) as session:
            session.add(
                HttpExecutionRecord(
                    id=run_id,
                    workspace_id=workspace_id,
                    environment_id=environment.id,
                    environment_name=environment.name,
                    base_url=environment.base_url,
                    variables_json=_dump(environment.variables),
                    secret_names_json=_dump(environment.secret_names),
                    method=input.method,
                    path_template=input.path,
                    headers_template_json=_dump(input.headers),
                    body_template=input.body,
                    timeout_seconds=input.timeout_seconds,
                    max_attempts=input.max_attempts,
                    assertions_json=_dump_assertions(input.assertions),
                    assertion_results_json="[]",
                    status="queued",
                    progress=0,
                    response_headers_json="{}",
                    created_at=created_at,
                )
            )
            self._add_event(
                session,
                run_id,
                level="info",
                code="HTTP_EXECUTION_QUEUED",
                message="HTTP 执行任务已进入队列。",
                attempt=None,
                now=created_at,
            )
            session.commit()
        result = self.get_run(workspace_id, run_id)
        if result is None:
            raise RuntimeError("HTTP execution was not persisted")
        return result

    def list_runs(self, workspace_id: str) -> list[HttpExecution]:
        with Session(self._engine) as session:
            records = session.exec(
                select(HttpExecutionRecord)
                .where(HttpExecutionRecord.workspace_id == workspace_id)
                .order_by(col(HttpExecutionRecord.created_at).desc())
            ).all()
            return [self._run(session, record) for record in records]

    def get_run(self, workspace_id: str, run_id: str) -> HttpExecution | None:
        with Session(self._engine) as session:
            record = session.get(HttpExecutionRecord, run_id)
            if record is None or record.workspace_id != workspace_id:
                return None
            return self._run(session, record)

    def get_any(self, run_id: str) -> HttpExecution | None:
        with Session(self._engine) as session:
            record = session.get(HttpExecutionRecord, run_id)
            return None if record is None else self._run(session, record)

    def recreate_run(
        self, source_run_id: str, new_run_id: str, *, created_at: datetime
    ) -> HttpExecution:
        with Session(self._engine) as session:
            source = session.get(HttpExecutionRecord, source_run_id)
            if source is None:
                raise LookupError(source_run_id)
            session.add(
                HttpExecutionRecord(
                    id=new_run_id,
                    workspace_id=source.workspace_id,
                    environment_id=source.environment_id,
                    environment_name=source.environment_name,
                    base_url=source.base_url,
                    variables_json=source.variables_json,
                    secret_names_json=source.secret_names_json,
                    method=source.method,
                    path_template=source.path_template,
                    headers_template_json=source.headers_template_json,
                    body_template=source.body_template,
                    timeout_seconds=source.timeout_seconds,
                    max_attempts=source.max_attempts,
                    assertions_json=source.assertions_json,
                    assertion_results_json="[]",
                    status="queued",
                    progress=0,
                    response_headers_json="{}",
                    created_at=created_at,
                )
            )
            self._add_event(
                session,
                new_run_id,
                level="info",
                code="HTTP_EXECUTION_RERUN_QUEUED",
                message="HTTP 执行任务已基于冻结模板重新进入队列。",
                attempt=None,
                now=created_at,
            )
            session.commit()
            workspace_id = source.workspace_id
        result = self.get_run(workspace_id, new_run_id)
        if result is None:
            raise RuntimeError("HTTP rerun was not persisted")
        return result

    def load_execution_input(self, run_id: str) -> HttpExecutionInput | None:
        with Session(self._engine) as session:
            record = session.get(HttpExecutionRecord, run_id)
            if record is None:
                return None
            return HttpExecutionInput(
                run_id=record.id,
                base_url=record.base_url,
                variables=_dict(record.variables_json),
                secret_names=_names(record.secret_names_json),
                method=record.method,  # type: ignore[arg-type]
                path_template=record.path_template,
                headers_template=_dict(record.headers_template_json),
                body_template=record.body_template,
                timeout_seconds=record.timeout_seconds,
                max_attempts=record.max_attempts,
                assertions=_assertions(record.assertions_json),
            )

    def mark_running(self, run_id: str, *, pid: int, now: datetime) -> None:
        self._transition(
            run_id,
            "running",
            20,
            now=now,
            pid=pid,
            event=("info", "HTTP_WORKER_STARTED", "HTTP 执行 Worker 已启动。", None),
        )

    def mark_passed(self, run_id: str, *, result: HttpExecutionResult, now: datetime) -> None:
        self.mark_completed(run_id, result=result, assertion_results=(), now=now)

    def mark_completed(
        self,
        run_id: str,
        *,
        result: HttpExecutionResult,
        assertion_results: tuple[HttpAssertionResult, ...],
        now: datetime,
    ) -> None:
        assertions_passed = all(item.passed for item in assertion_results)
        self._transition(
            run_id,
            "passed" if assertions_passed else "failed",
            100,
            now=now,
            result=result,
            assertion_results=assertion_results,
            code=None if assertions_passed else "HTTP_ASSERTION_FAILED",
            message=None if assertions_passed else "一个或多个 HTTP 断言未通过。",
            event=(
                "info" if assertions_passed else "warning",
                "HTTP_ASSERTIONS_PASSED" if assertions_passed else "HTTP_ASSERTIONS_FAILED",
                (
                    "HTTP 响应与全部断言均已完成。"
                    if assertions_passed
                    else "HTTP 响应已收到。存在未通过断言。"
                ),
                None,
            ),
        )

    def append_event(
        self,
        run_id: str,
        *,
        level: str,
        code: str,
        message: str,
        attempt: int | None,
        now: datetime,
    ) -> None:
        with Session(self._engine) as session:
            if session.get(HttpExecutionRecord, run_id) is None:
                return
            self._add_event(session, run_id, level, code, message, attempt, now)
            session.commit()

    def mark_failed(self, run_id: str, *, code: str, message: str, now: datetime) -> None:
        self._transition(
            run_id,
            "failed",
            100,
            now=now,
            code=code,
            message=message,
            event=("error", code, message, None),
        )

    def mark_error(self, run_id: str, *, code: str, message: str, now: datetime) -> None:
        self._transition(
            run_id,
            "error",
            100,
            now=now,
            code=code,
            message=message,
            event=("error", code, message, None),
        )

    def mark_timeout(self, run_id: str, *, now: datetime) -> None:
        self._transition(
            run_id,
            "timeout",
            100,
            now=now,
            code="HTTP_EXECUTION_TIMEOUT",
            message="HTTP 执行任务超时。",
            event=("error", "HTTP_EXECUTION_TIMEOUT", "HTTP 执行任务超时。", None),
        )

    def mark_cancelled(self, run_id: str, *, now: datetime) -> None:
        self._transition(
            run_id,
            "cancelled",
            100,
            now=now,
            event=("warning", "HTTP_EXECUTION_CANCELLED", "HTTP 执行任务已取消。", None),
        )

    def recover_interrupted(self, *, now: datetime) -> None:
        with Session(self._engine) as session:
            records = session.exec(
                select(HttpExecutionRecord).where(
                    col(HttpExecutionRecord.status).in_(["queued", "running"])
                )
            ).all()
            for record in records:
                self._transition_in_session(
                    record,
                    "error",
                    100,
                    now=now,
                    code="HTTP_WORKER_INTERRUPTED",
                    message="HTTP 执行任务因应用中断而结束。",
                )
                self._add_event(
                    session,
                    record.id,
                    "error",
                    "HTTP_WORKER_INTERRUPTED",
                    "HTTP 执行任务因应用中断而结束。",
                    None,
                    now,
                )
                session.add(record)
            session.commit()

    def _transition(
        self,
        run_id: str,
        status: HttpExecutionStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        code: str | None = None,
        message: str | None = None,
        result: HttpExecutionResult | None = None,
        assertion_results: tuple[HttpAssertionResult, ...] | None = None,
        event: tuple[str, str, str, int | None] | None = None,
    ) -> None:
        with Session(self._engine) as session:
            record = session.get(HttpExecutionRecord, run_id)
            if record is None or record.status in TERMINAL_HTTP_EXECUTION_STATUSES:
                return
            self._transition_in_session(
                record,
                status,
                progress,
                now=now,
                pid=pid,
                code=code,
                message=message,
                result=result,
                assertion_results=assertion_results,
            )
            if event is not None:
                self._add_event(session, run_id, *event, now)
            session.add(record)
            session.commit()

    @staticmethod
    def _transition_in_session(
        record: HttpExecutionRecord,
        status: HttpExecutionStatus,
        progress: int,
        *,
        now: datetime,
        pid: int | None = None,
        code: str | None = None,
        message: str | None = None,
        result: HttpExecutionResult | None = None,
        assertion_results: tuple[HttpAssertionResult, ...] | None = None,
    ) -> None:
        record.status = status
        record.progress = progress
        if pid is not None:
            record.pid = pid
        if status == "running" and record.started_at is None:
            record.started_at = now
        if status in TERMINAL_HTTP_EXECUTION_STATUSES:
            record.finished_at = now
        record.error_code = code
        record.error_message = message
        if result is not None:
            record.response_status_code = result.status_code
            record.response_headers_json = _dump(result.headers)
            record.response_body = result.body
            record.response_body_encoding = result.body_encoding
            record.response_size_bytes = result.size_bytes
            record.duration_ms = result.duration_ms
        if assertion_results is not None:
            record.assertion_results_json = _dump_assertion_results(assertion_results)

    @staticmethod
    def _add_event(
        session: Session,
        run_id: str,
        level: str,
        code: str,
        message: str,
        attempt: int | None,
        now: datetime,
    ) -> None:
        latest = session.exec(
            select(HttpExecutionEventRecord)
            .where(HttpExecutionEventRecord.run_id == run_id)
            .order_by(col(HttpExecutionEventRecord.ordinal).desc())
        ).first()
        session.add(
            HttpExecutionEventRecord(
                id=str(uuid4()),
                run_id=run_id,
                ordinal=1 if latest is None else latest.ordinal + 1,
                level=level,
                code=code,
                message=message,
                attempt=attempt,
                created_at=now,
            )
        )

    @staticmethod
    def _environment(record: HttpEnvironmentRecord) -> HttpEnvironment:
        return HttpEnvironment(
            id=record.id,
            workspace_id=record.workspace_id,
            name=record.name,
            base_url=record.base_url,
            variables=_dict(record.variables_json),
            secret_names=_names(record.secret_names_json),
            created_at=_utc(record.created_at) or record.created_at,
            updated_at=_utc(record.updated_at) or record.updated_at,
        )

    @staticmethod
    def _run(session: Session, record: HttpExecutionRecord) -> HttpExecution:
        event_records = session.exec(
            select(HttpExecutionEventRecord)
            .where(HttpExecutionEventRecord.run_id == record.id)
            .order_by(col(HttpExecutionEventRecord.ordinal))
        ).all()
        return HttpExecution(
            id=record.id,
            workspace_id=record.workspace_id,
            environment_id=record.environment_id,
            environment_name=record.environment_name,
            method=record.method,  # type: ignore[arg-type]
            base_url=record.base_url,
            path_template=record.path_template,
            headers_template=_dict(record.headers_template_json),
            body_template=record.body_template,
            timeout_seconds=record.timeout_seconds,
            status=record.status,  # type: ignore[arg-type]
            progress=record.progress,
            pid=record.pid,
            response_status_code=record.response_status_code,
            response_headers=_dict(record.response_headers_json),
            response_body=record.response_body,
            response_body_encoding=record.response_body_encoding,  # type: ignore[arg-type]
            response_size_bytes=record.response_size_bytes,
            duration_ms=record.duration_ms,
            error_code=record.error_code,
            error_message=record.error_message,
            created_at=_utc(record.created_at) or record.created_at,
            started_at=_utc(record.started_at),
            finished_at=_utc(record.finished_at),
            max_attempts=record.max_attempts,
            assertions=_assertions(record.assertions_json),
            assertion_results=_assertion_results(record.assertion_results_json),
            events=tuple(
                HttpExecutionEvent(
                    id=item.id,
                    ordinal=item.ordinal,
                    level=item.level,  # type: ignore[arg-type]
                    code=item.code,
                    message=item.message,
                    attempt=item.attempt,
                    created_at=_utc(item.created_at) or item.created_at,
                )
                for item in event_records
            ),
        )

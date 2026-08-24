from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from backend.app.core.errors import AppError
from backend.app.domain.http_execution import HttpEnvironment, HttpTemplateError, resolve_template
from backend.app.domain.websocket_execution import (
    WebSocketExecution,
    WebSocketExecutionStartInput,
    WebSocketExecutionTaskRequest,
    build_websocket_url,
)
from backend.app.domain.workspace import Workspace

MAX_HEADERS = 50
MAX_HEADER_VALUE_LENGTH = 8192
MAX_MESSAGE_BYTES = 1024 * 1024
MAX_TOTAL_MESSAGE_BYTES = 2 * 1024 * 1024
MAX_MESSAGES = 10
MAX_RECEIVE_MESSAGES = 20
MAX_ASSERTIONS = 20
HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")


class WorkspaceReader(Protocol):
    def get(self, workspace_id: str) -> Workspace | None: ...


class HttpEnvironmentReader(Protocol):
    def get_environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment | None: ...


class WebSocketExecutionRepository(Protocol):
    def create_run(
        self,
        *,
        run_id: str,
        workspace_id: str,
        environment: HttpEnvironment,
        input: WebSocketExecutionStartInput,
        created_at: datetime,
    ) -> WebSocketExecution: ...

    def list_runs(self, workspace_id: str) -> list[WebSocketExecution]: ...

    def get_run(self, workspace_id: str, run_id: str) -> WebSocketExecution | None: ...


class WebSocketWorker(Protocol):
    def recover_interrupted(self) -> None: ...

    def launch(self, request: WebSocketExecutionTaskRequest) -> None: ...

    def cancel(self, run_id: str) -> None: ...


class WebSocketExecutionUseCases(Protocol):
    def start(
        self, workspace_id: str, input: WebSocketExecutionStartInput
    ) -> WebSocketExecution: ...

    def list_runs(self, workspace_id: str) -> list[WebSocketExecution]: ...

    def get_run(self, workspace_id: str, run_id: str) -> WebSocketExecution: ...

    def cancel(self, workspace_id: str, run_id: str) -> WebSocketExecution: ...


class WebSocketExecutionService:
    def __init__(
        self,
        workspaces: WorkspaceReader,
        environments: HttpEnvironmentReader,
        repository: WebSocketExecutionRepository,
        worker: WebSocketWorker,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._environments = environments
        self._repository = repository
        self._worker = worker
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._recovered = False

    def start(self, workspace_id: str, input: WebSocketExecutionStartInput) -> WebSocketExecution:
        self._workspace(workspace_id)
        self._ensure_recovered()
        environment = self._environment(workspace_id, input.environment_id)
        normalized = self._validate_input(input, environment)
        run = self._repository.create_run(
            run_id=self._id_factory(),
            workspace_id=workspace_id,
            environment=environment,
            input=normalized,
            created_at=self._clock(),
        )
        self._worker.launch(WebSocketExecutionTaskRequest(run.id))
        return run

    def list_runs(self, workspace_id: str) -> list[WebSocketExecution]:
        self._workspace(workspace_id)
        self._ensure_recovered()
        return self._repository.list_runs(workspace_id)

    def get_run(self, workspace_id: str, run_id: str) -> WebSocketExecution:
        self._workspace(workspace_id)
        self._ensure_recovered()
        run = self._repository.get_run(workspace_id, run_id)
        if run is None:
            raise AppError(
                code="WEBSOCKET_EXECUTION_NOT_FOUND",
                message="未找到该 WebSocket 执行任务。",
                status_code=404,
            )
        return run

    def cancel(self, workspace_id: str, run_id: str) -> WebSocketExecution:
        run = self.get_run(workspace_id, run_id)
        if not run.can_cancel:
            raise AppError(
                code="WEBSOCKET_EXECUTION_FINISHED",
                message="该 WebSocket 执行任务已经结束。",
                status_code=409,
            )
        self._worker.cancel(run.id)
        return self._repository.get_run(workspace_id, run.id) or run

    def _workspace(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise AppError(
                code="WORKSPACE_NOT_FOUND", message="未找到该工作空间。", status_code=404
            )
        return workspace

    def _environment(self, workspace_id: str, environment_id: str) -> HttpEnvironment:
        environment = self._environments.get_environment(workspace_id, environment_id)
        if environment is None:
            raise AppError(
                code="HTTP_ENVIRONMENT_NOT_FOUND",
                message="未找到该 HTTP/WebSocket 环境。",
                status_code=404,
            )
        return environment

    @staticmethod
    def _validate_input(
        input: WebSocketExecutionStartInput, environment: HttpEnvironment
    ) -> WebSocketExecutionStartInput:
        messages = (input.message, *input.additional_messages)
        try:
            assertions = tuple(item.validate() for item in input.assertions)
        except ValueError as exception:
            raise AppError(
                code="WEBSOCKET_REQUEST_INVALID",
                message="WebSocket 消息、心跳、重连或断言配置不正确。",
                status_code=422,
            ) from exception
        if (
            not 1 <= input.timeout_seconds <= 60
            or not 1 <= len(messages) <= MAX_MESSAGES
            or any(not item for item in messages)
            or not 1 <= input.receive_count <= MAX_RECEIVE_MESSAGES
            or (
                input.ping_interval_seconds is not None
                and not 5 <= input.ping_interval_seconds <= 60
            )
            or input.max_reconnect_attempts not in {0, 1}
            or len(assertions) > MAX_ASSERTIONS
            or any(item.message_index >= input.receive_count for item in assertions)
        ):
            raise AppError(
                code="WEBSOCKET_REQUEST_INVALID",
                message="WebSocket 消息、心跳、重连或断言配置不正确。",
                status_code=422,
            )
        if (
            any(len(item.encode("utf-8")) > MAX_MESSAGE_BYTES for item in messages)
            or sum(len(item.encode("utf-8")) for item in messages) > MAX_TOTAL_MESSAGE_BYTES
            or len(input.headers) > MAX_HEADERS
        ):
            raise AppError(
                code="WEBSOCKET_REQUEST_INVALID",
                message="WebSocket 请求超过大小或请求头数量限制。",
                status_code=422,
            )
        if any(
            HEADER_NAME_PATTERN.fullmatch(name) is None
            or len(value) > MAX_HEADER_VALUE_LENGTH
            or "\r" in value
            or "\n" in value
            for name, value in input.headers.items()
        ):
            raise AppError(
                code="WEBSOCKET_REQUEST_INVALID",
                message="WebSocket 握手请求头格式不正确。",
                status_code=422,
            )
        dummy_variables = {name: "value" for name in environment.variables}
        dummy_secrets = {name: "secret" for name in environment.secret_names}
        try:
            path = resolve_template(input.path, variables=dummy_variables, secrets=dummy_secrets)
            build_websocket_url(environment.base_url, path)
            for value in (*input.headers.values(), *messages):
                resolve_template(value, variables=dummy_variables, secrets=dummy_secrets)
        except (HttpTemplateError, ValueError) as exception:
            raise AppError(
                code="WEBSOCKET_REQUEST_INVALID",
                message="WebSocket 路径或模板格式不正确。",
                status_code=422,
            ) from exception
        return WebSocketExecutionStartInput(
            environment_id=environment.id,
            path=input.path,
            headers=dict(input.headers),
            message=input.message,
            timeout_seconds=input.timeout_seconds,
            additional_messages=tuple(input.additional_messages),
            receive_count=input.receive_count,
            ping_interval_seconds=input.ping_interval_seconds,
            max_reconnect_attempts=input.max_reconnect_attempts,
            assertions=assertions,
        )

    def _ensure_recovered(self) -> None:
        if self._recovered:
            return
        self._worker.recover_interrupted()
        self._recovered = True

from __future__ import annotations

import logging
import multiprocessing
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from multiprocessing.process import BaseProcess
from typing import Protocol

from backend.app.application.credentials import CredentialStoreUnavailableError
from backend.app.domain.http_execution import HttpTemplateError, resolve_template
from backend.app.domain.websocket_execution import (
    WebSocketExecutionInput,
    WebSocketExecutionResult,
    WebSocketExecutionTaskRequest,
    build_websocket_url,
    evaluate_websocket_assertions,
)
from backend.app.infrastructure.credentials import KeyringHttpSecretStore
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.websocket_execution import SqlModelWebSocketExecutionRepository
from backend.app.infrastructure.websocket_runner import WebSocketRunner, WebSocketRunnerError

logger = logging.getLogger(__name__)


class HttpSecretReader(Protocol):
    def get(self, environment_id: str, name: str) -> str | None: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _run_request(
    execution: WebSocketExecutionInput,
    *,
    environment_id: str,
    store_factory: Callable[[], HttpSecretReader] = KeyringHttpSecretStore,
    runner: WebSocketRunner | None = None,
) -> WebSocketExecutionResult:
    store = store_factory()
    secrets: dict[str, str] = {}
    try:
        for name in execution.secret_names:
            value = store.get(environment_id, name)
            if value is None:
                raise WebSocketRunnerError("secret_missing")
            secrets[name] = value
    except CredentialStoreUnavailableError as exception:
        raise WebSocketRunnerError("credential_store_unavailable") from exception
    try:
        path = resolve_template(
            execution.path_template, variables=execution.variables, secrets=secrets
        )
        headers = {
            name: resolve_template(value, variables=execution.variables, secrets=secrets)
            for name, value in execution.headers_template.items()
        }
        message = resolve_template(
            execution.message_template, variables=execution.variables, secrets=secrets
        )
        additional_messages = tuple(
            resolve_template(item, variables=execution.variables, secrets=secrets)
            for item in execution.additional_message_templates
        )
        url = build_websocket_url(execution.base_url, path)
    except (HttpTemplateError, ValueError) as exception:
        raise WebSocketRunnerError("template_invalid") from exception
    result = (runner or WebSocketRunner()).execute(
        url=url,
        headers=headers,
        message=message,
        additional_messages=additional_messages,
        receive_count=execution.receive_count,
        ping_interval_seconds=execution.ping_interval_seconds,
        max_reconnect_attempts=execution.max_reconnect_attempts,
        timeout_seconds=execution.timeout_seconds,
        secrets=tuple(secrets.values()),
    )
    assertion_results = evaluate_websocket_assertions(execution.assertions, result.responses)
    return WebSocketExecutionResult(
        result.message,
        result.encoding,
        result.size_bytes,
        result.duration_ms,
        result.responses,
        assertion_results,
        result.attempt_count,
    )


def _failure(reason: str) -> tuple[str, str]:
    failures = {
        "credential_store_unavailable": (
            "WEBSOCKET_CREDENTIAL_STORE_UNAVAILABLE",
            "操作系统凭据库当前不可用。",
        ),
        "secret_missing": ("WEBSOCKET_SECRET_MISSING", "请求引用的安全变量未配置。"),
        "template_invalid": ("WEBSOCKET_TEMPLATE_INVALID", "WebSocket 模板变量无法解析。"),
        "timeout": ("WEBSOCKET_MESSAGE_TIMEOUT", "等待 WebSocket 消息超时。"),
        "unavailable": ("WEBSOCKET_TARGET_UNAVAILABLE", "无法连接目标 WebSocket 服务。"),
        "response_too_large": (
            "WEBSOCKET_MESSAGE_TOO_LARGE",
            "WebSocket 响应消息超过 2 MiB 限制。",
        ),
    }
    return failures.get(reason, ("WEBSOCKET_REQUEST_FAILED", "WebSocket 请求执行失败。"))


def run_websocket_execution_job(database_url: str, request: WebSocketExecutionTaskRequest) -> None:
    repository = SqlModelWebSocketExecutionRepository(create_database_engine(database_url))
    execution = repository.load_execution_input(request.run_id)
    run = repository.get_any(request.run_id)
    if execution is None or run is None or run.environment_id is None:
        repository.mark_failed(
            request.run_id,
            code="WEBSOCKET_INPUT_UNAVAILABLE",
            message="无法读取本次 WebSocket 执行输入。",
            now=_now(),
        )
        return
    repository.mark_running(request.run_id, pid=os.getpid(), now=_now())
    try:
        result = _run_request(execution, environment_id=run.environment_id)
    except WebSocketRunnerError as exception:
        code, message = _failure(exception.reason)
        repository.mark_failed(request.run_id, code=code, message=message, now=_now())
        return
    except Exception as exception:
        logger.error(
            "WebSocket execution worker failed",
            extra={"run_id": request.run_id, "error_type": type(exception).__name__},
        )
        repository.mark_error(
            request.run_id,
            code="WEBSOCKET_WORKER_ERROR",
            message="WebSocket 执行进程发生错误。",
            now=_now(),
        )
        return
    repository.mark_passed(request.run_id, result=result, now=_now())


class WebSocketExecutionWorkerManager:
    def __init__(
        self,
        repository: SqlModelWebSocketExecutionRepository,
        *,
        database_url: str,
        timeout_seconds: int,
    ) -> None:
        self._repository = repository
        self._database_url = database_url
        self._timeout_seconds = timeout_seconds
        self._context = multiprocessing.get_context("spawn")
        self._processes: dict[str, BaseProcess] = {}
        self._lock = threading.Lock()

    def recover_interrupted(self) -> None:
        self._repository.recover_interrupted(now=_now())

    def launch(self, request: WebSocketExecutionTaskRequest) -> None:
        process = self._context.Process(
            target=run_websocket_execution_job,
            args=(self._database_url, request),
            daemon=True,
            name=f"websocket-execution-{request.run_id[:8]}",
        )
        try:
            process.start()
        except Exception as exception:
            logger.error(
                "WebSocket execution worker start failed",
                extra={"run_id": request.run_id, "error_type": type(exception).__name__},
            )
            self._repository.mark_error(
                request.run_id,
                code="WEBSOCKET_WORKER_START_FAILED",
                message="无法启动 WebSocket 执行进程。",
                now=_now(),
            )
            raise
        with self._lock:
            self._processes[request.run_id] = process
        threading.Thread(
            target=self._supervise,
            args=(request.run_id, process),
            daemon=True,
            name=f"websocket-execution-supervisor-{request.run_id[:8]}",
        ).start()

    def cancel(self, run_id: str) -> None:
        with self._lock:
            process = self._processes.pop(run_id, None)
        self._repository.mark_cancelled(run_id, now=_now())
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=5)

    def _supervise(self, run_id: str, process: BaseProcess) -> None:
        process.join(timeout=self._timeout_seconds)
        with self._lock:
            if self._processes.get(run_id) is not process:
                return
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            self._repository.mark_timeout(run_id, now=_now())
        elif process.exitcode not in (0, None):
            self._repository.mark_error(
                run_id,
                code="WEBSOCKET_WORKER_CRASHED",
                message="WebSocket 执行进程意外退出。",
                now=_now(),
            )
        with self._lock:
            if self._processes.get(run_id) is process:
                self._processes.pop(run_id, None)

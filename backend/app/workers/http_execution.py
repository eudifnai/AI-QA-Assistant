from __future__ import annotations

import logging
import multiprocessing
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from multiprocessing.process import BaseProcess

from backend.app.application.credentials import CredentialStoreUnavailableError
from backend.app.domain.http_execution import (
    HttpExecutionInput,
    HttpExecutionResult,
    HttpExecutionTaskRequest,
    HttpTemplateError,
    evaluate_http_assertions,
    resolve_template,
)
from backend.app.infrastructure.credentials import KeyringHttpSecretStore
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.http_execution import SqlModelHttpExecutionRepository
from backend.app.infrastructure.http_runner import HttpRunnerError, StdlibHttpRunner

logger = logging.getLogger(__name__)
RETRYABLE_FAILURES = frozenset({"timeout", "unavailable"})
RETRYABLE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _now() -> datetime:
    return datetime.now(UTC)


def _run_request(
    execution: HttpExecutionInput,
    *,
    environment_id: str,
    store_factory: Callable[[], KeyringHttpSecretStore] = KeyringHttpSecretStore,
    runner: StdlibHttpRunner | None = None,
) -> HttpExecutionResult:
    store = store_factory()
    secrets: dict[str, str] = {}
    try:
        for name in execution.secret_names:
            value = store.get(environment_id, name)
            if value is None:
                raise HttpRunnerError("secret_missing")
            secrets[name] = value
    except CredentialStoreUnavailableError as exception:
        raise HttpRunnerError("credential_store_unavailable") from exception
    try:
        path = resolve_template(
            execution.path_template,
            variables=execution.variables,
            secrets=secrets,
        )
        headers = {
            name: resolve_template(value, variables=execution.variables, secrets=secrets)
            for name, value in execution.headers_template.items()
        }
        body = (
            None
            if execution.body_template is None
            else resolve_template(
                execution.body_template,
                variables=execution.variables,
                secrets=secrets,
            )
        )
    except HttpTemplateError as exception:
        raise HttpRunnerError("template_invalid") from exception
    return (runner or StdlibHttpRunner()).execute(
        method=execution.method,
        url=f"{execution.base_url}{path}",
        headers=headers,
        body=body,
        timeout_seconds=execution.timeout_seconds,
        secrets=tuple(secrets.values()),
    )


def _failure(reason: str) -> tuple[str, str]:
    failures = {
        "credential_store_unavailable": (
            "HTTP_CREDENTIAL_STORE_UNAVAILABLE",
            "操作系统凭据库当前不可用。",
        ),
        "secret_missing": ("HTTP_SECRET_MISSING", "请求引用的安全变量未配置。"),
        "template_invalid": ("HTTP_TEMPLATE_INVALID", "请求模板变量无法解析。"),
        "timeout": ("HTTP_REQUEST_TIMEOUT", "等待目标 HTTP 服务响应超时。"),
        "unavailable": ("HTTP_TARGET_UNAVAILABLE", "无法连接目标 HTTP 服务。"),
        "response_too_large": (
            "HTTP_RESPONSE_TOO_LARGE",
            "目标 HTTP 响应超过 2 MiB 限制。",
        ),
    }
    return failures.get(reason, ("HTTP_REQUEST_FAILED", "HTTP 请求执行失败。"))


def _execute_with_retries(
    execution: HttpExecutionInput,
    *,
    environment_id: str,
    event: Callable[[str, str, str, int], None],
    sleeper: Callable[[float], None] = time.sleep,
) -> HttpExecutionResult:
    max_attempts = execution.max_attempts if execution.method in RETRYABLE_METHODS else 1
    for attempt in range(1, max_attempts + 1):
        event("info", "HTTP_REQUEST_ATTEMPT_STARTED", "HTTP 请求尝试已开始。", attempt)
        try:
            return _run_request(execution, environment_id=environment_id)
        except HttpRunnerError as exception:
            if exception.reason not in RETRYABLE_FAILURES or attempt >= max_attempts:
                raise
            event(
                "warning",
                "HTTP_REQUEST_RETRY_SCHEDULED",
                "目标暂时不可用。将进行下一次安全重试。",
                attempt,
            )
            sleeper(0.25 * attempt)
    raise HttpRunnerError("unavailable")


def run_http_execution_job(database_url: str, request: HttpExecutionTaskRequest) -> None:
    repository = SqlModelHttpExecutionRepository(create_database_engine(database_url))
    execution = repository.load_execution_input(request.run_id)
    run = repository.get_any(request.run_id)
    if execution is None or run is None or run.environment_id is None:
        repository.mark_failed(
            request.run_id,
            code="HTTP_INPUT_UNAVAILABLE",
            message="无法读取本次 HTTP 执行输入。",
            now=_now(),
        )
        return
    repository.mark_running(request.run_id, pid=os.getpid(), now=_now())
    try:
        result = _execute_with_retries(
            execution,
            environment_id=run.environment_id,
            event=lambda level, code, message, attempt: repository.append_event(
                request.run_id,
                level=level,
                code=code,
                message=message,
                attempt=attempt,
                now=_now(),
            ),
        )
        assertion_results = evaluate_http_assertions(
            execution.assertions,
            status_code=result.status_code,
            headers=result.headers,
            body=result.body,
            body_encoding=result.body_encoding,
        )
    except HttpRunnerError as exception:
        code, message = _failure(exception.reason)
        repository.mark_failed(request.run_id, code=code, message=message, now=_now())
        return
    except Exception as exception:
        logger.error(
            "HTTP execution worker failed",
            extra={"run_id": request.run_id, "error_type": type(exception).__name__},
        )
        repository.mark_error(
            request.run_id,
            code="HTTP_WORKER_ERROR",
            message="HTTP 执行进程发生错误。",
            now=_now(),
        )
        return
    repository.mark_completed(
        request.run_id,
        result=result,
        assertion_results=assertion_results,
        now=_now(),
    )


class HttpExecutionWorkerManager:
    def __init__(
        self,
        repository: SqlModelHttpExecutionRepository,
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

    def launch(self, request: HttpExecutionTaskRequest) -> None:
        process = self._context.Process(
            target=run_http_execution_job,
            args=(self._database_url, request),
            daemon=True,
            name=f"http-execution-{request.run_id[:8]}",
        )
        try:
            process.start()
        except Exception as exception:
            logger.error(
                "HTTP execution worker start failed",
                extra={"run_id": request.run_id, "error_type": type(exception).__name__},
            )
            self._repository.mark_error(
                request.run_id,
                code="HTTP_WORKER_START_FAILED",
                message="无法启动 HTTP 执行进程。",
                now=_now(),
            )
            raise
        with self._lock:
            self._processes[request.run_id] = process
        threading.Thread(
            target=self._supervise,
            args=(request.run_id, process),
            daemon=True,
            name=f"http-execution-supervisor-{request.run_id[:8]}",
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
                code="HTTP_WORKER_CRASHED",
                message="HTTP 执行进程意外退出。",
                now=_now(),
            )
        with self._lock:
            if self._processes.get(run_id) is process:
                self._processes.pop(run_id, None)
